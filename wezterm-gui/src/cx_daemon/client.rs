//! CX Daemon Client
//!
//! Handles communication with the CX Linux daemon over Unix sockets.
//! Includes automatic reconnection with exponential backoff and
//! connection state change notifications.

#![allow(dead_code)]

use super::protocol::{
    AgentInfo, ContextType, DaemonError, DaemonRequest, DaemonResponse, TerminalContext,
};
use super::{user_socket_path, DEFAULT_SOCKET_PATH};
use std::io::{BufRead, BufReader, Write};
#[cfg(unix)]
use std::os::unix::net::UnixStream;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::broadcast;

/// Connection state for the daemon client
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConnectionState {
    /// Not connected to daemon
    Disconnected,
    /// Attempting to connect
    Connecting,
    /// Successfully connected
    Connected,
    /// Reconnecting after disconnect
    Reconnecting,
    /// Connection failed (with retry count)
    Failed,
}

/// Event emitted when connection state changes
#[derive(Debug, Clone)]
pub struct ConnectionStateEvent {
    pub state: ConnectionState,
    pub message: String,
    pub retry_count: u32,
}

/// Configuration for reconnection behavior
#[derive(Debug, Clone)]
pub struct ReconnectConfig {
    /// Enable automatic reconnection
    pub enabled: bool,
    /// Initial delay before first retry
    pub initial_delay: Duration,
    /// Maximum delay between retries
    pub max_delay: Duration,
    /// Maximum number of retry attempts (0 = infinite)
    pub max_retries: u32,
    /// Multiplier for exponential backoff
    pub backoff_multiplier: f64,
}

impl Default for ReconnectConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            initial_delay: Duration::from_millis(100),
            max_delay: Duration::from_secs(30),
            max_retries: 10,
            backoff_multiplier: 2.0,
        }
    }
}

/// Client for communicating with the CX Linux daemon
pub struct CXDaemonClient {
    /// Path to the daemon socket
    socket_path: PathBuf,
    /// Whether currently connected
    connected: Arc<AtomicBool>,
    /// Terminal ID for this instance
    terminal_id: String,
    /// Connection timeout
    timeout: Duration,
    /// Reconnection configuration
    reconnect_config: ReconnectConfig,
    /// Current retry count
    retry_count: Arc<AtomicU32>,
    /// Connection state broadcaster
    state_tx: broadcast::Sender<ConnectionStateEvent>,
    /// Current connection state
    current_state: Arc<std::sync::Mutex<ConnectionState>>,
}

impl CXDaemonClient {
    /// Create a new daemon client with default socket path
    pub fn new() -> Self {
        Self::with_socket_path(Self::find_socket_path())
    }

    /// Create a new daemon client with a specific socket path
    pub fn with_socket_path(socket_path: PathBuf) -> Self {
        let (state_tx, _) = broadcast::channel(16);
        Self {
            socket_path,
            connected: Arc::new(AtomicBool::new(false)),
            terminal_id: uuid::Uuid::new_v4().to_string(),
            timeout: Duration::from_secs(5),
            reconnect_config: ReconnectConfig::default(),
            retry_count: Arc::new(AtomicU32::new(0)),
            state_tx,
            current_state: Arc::new(std::sync::Mutex::new(ConnectionState::Disconnected)),
        }
    }

    /// Create a new daemon client with custom configuration
    pub fn with_config(socket_path: PathBuf, reconnect_config: ReconnectConfig) -> Self {
        let (state_tx, _) = broadcast::channel(16);
        Self {
            socket_path,
            connected: Arc::new(AtomicBool::new(false)),
            terminal_id: uuid::Uuid::new_v4().to_string(),
            timeout: Duration::from_secs(5),
            reconnect_config,
            retry_count: Arc::new(AtomicU32::new(0)),
            state_tx,
            current_state: Arc::new(std::sync::Mutex::new(ConnectionState::Disconnected)),
        }
    }

    /// Find the best socket path to use
    fn find_socket_path() -> PathBuf {
        // Check system socket first
        let system_path = PathBuf::from(DEFAULT_SOCKET_PATH);
        if system_path.exists() {
            return system_path;
        }

        // Fall back to user socket
        let user_path = user_socket_path();
        if user_path.exists() {
            return user_path;
        }

        // Return system path even if it doesn't exist (for error messages)
        system_path
    }

    /// Check if the daemon is available
    pub fn is_available() -> bool {
        let system_path = PathBuf::from(DEFAULT_SOCKET_PATH);
        if system_path.exists() {
            return Self::test_connection(&system_path);
        }

        let user_path = user_socket_path();
        if user_path.exists() {
            return Self::test_connection(&user_path);
        }

        false
    }

    /// Test if a socket is responsive
    fn test_connection(path: &PathBuf) -> bool {
        if let Ok(stream) = UnixStream::connect(path) {
            let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
            let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));

            // Try to send a ping
            let mut stream = stream;
            let request = DaemonRequest::Ping;
            if let Ok(json) = request.to_json_line() {
                if stream.write_all(json.as_bytes()).is_ok() {
                    let mut reader = BufReader::new(&stream);
                    let mut response = String::new();
                    if reader.read_line(&mut response).is_ok() {
                        return DaemonResponse::from_json(&response)
                            .map(|r| matches!(r, DaemonResponse::Pong { .. }))
                            .unwrap_or(false);
                    }
                }
            }
        }
        false
    }

    /// Subscribe to connection state changes
    pub fn subscribe_state_changes(&self) -> broadcast::Receiver<ConnectionStateEvent> {
        self.state_tx.subscribe()
    }

    /// Get current connection state
    pub fn connection_state(&self) -> ConnectionState {
        *self.current_state.lock().unwrap()
    }

    /// Emit a state change event
    fn set_state(&self, state: ConnectionState, message: &str) {
        let retry_count = self.retry_count.load(Ordering::SeqCst);
        {
            let mut current = self.current_state.lock().unwrap();
            *current = state;
        }

        let event = ConnectionStateEvent {
            state,
            message: message.to_string(),
            retry_count,
        };

        // Ignore send errors (no receivers)
        let _ = self.state_tx.send(event);

        log::debug!("Daemon connection state: {:?} - {}", state, message);
    }

    /// Connect to the daemon
    pub async fn connect() -> Result<Self, DaemonError> {
        let client = Self::new();
        client.set_state(ConnectionState::Connecting, "Attempting connection");
        client.register_terminal().await?;
        Ok(client)
    }

    /// Connect to the daemon with automatic reconnection
    pub async fn connect_with_reconnect() -> Result<Self, DaemonError> {
        let client = Self::new();
        client.connect_internal().await
    }

    /// Internal connect with retry logic
    async fn connect_internal(&self) -> Result<Self, DaemonError> {
        let mut delay = self.reconnect_config.initial_delay;
        let max_retries = self.reconnect_config.max_retries;

        loop {
            let retry_count = self.retry_count.load(Ordering::SeqCst);

            if max_retries > 0 && retry_count >= max_retries {
                self.set_state(ConnectionState::Failed, "Max retries exceeded");
                return Err(DaemonError::ConnectionFailed(format!(
                    "Failed to connect after {} attempts",
                    retry_count
                )));
            }

            self.set_state(
                if retry_count == 0 {
                    ConnectionState::Connecting
                } else {
                    ConnectionState::Reconnecting
                },
                &format!("Attempt {} of {}", retry_count + 1, max_retries),
            );

            match self.register_terminal().await {
                Ok(()) => {
                    self.retry_count.store(0, Ordering::SeqCst);
                    return Ok(Self {
                        socket_path: self.socket_path.clone(),
                        connected: self.connected.clone(),
                        terminal_id: self.terminal_id.clone(),
                        timeout: self.timeout,
                        reconnect_config: self.reconnect_config.clone(),
                        retry_count: self.retry_count.clone(),
                        state_tx: self.state_tx.clone(),
                        current_state: self.current_state.clone(),
                    });
                }
                Err(e) => {
                    log::warn!(
                        "Connection attempt {} failed: {}",
                        retry_count + 1,
                        e
                    );

                    if !self.reconnect_config.enabled {
                        self.set_state(ConnectionState::Failed, &e.to_string());
                        return Err(e);
                    }

                    self.retry_count.fetch_add(1, Ordering::SeqCst);

                    // Exponential backoff
                    tokio::time::sleep(delay).await;
                    delay = Duration::from_secs_f64(
                        (delay.as_secs_f64() * self.reconnect_config.backoff_multiplier)
                            .min(self.reconnect_config.max_delay.as_secs_f64()),
                    );
                }
            }
        }
    }

    /// Register this terminal with the daemon
    async fn register_terminal(&self) -> Result<(), DaemonError> {
        let request = DaemonRequest::RegisterTerminal {
            terminal_id: self.terminal_id.clone(),
            pid: std::process::id(),
            tty: std::env::var("TTY").ok(),
        };

        match self.send_request(&request).await {
            Ok(DaemonResponse::Success { .. }) => {
                self.connected.store(true, Ordering::SeqCst);
                self.set_state(ConnectionState::Connected, "Successfully connected");
                Ok(())
            }
            Ok(DaemonResponse::Error { message, .. }) => {
                Err(DaemonError::ConnectionFailed(message))
            }
            Ok(_) => Err(DaemonError::Protocol("Unexpected response".to_string())),
            Err(e) => Err(e),
        }
    }

    /// Unregister this terminal from the daemon
    pub async fn disconnect(&self) -> Result<(), DaemonError> {
        if !self.connected.load(Ordering::SeqCst) {
            return Ok(());
        }

        let request = DaemonRequest::UnregisterTerminal {
            terminal_id: self.terminal_id.clone(),
        };

        let _ = self.send_request(&request).await;
        self.connected.store(false, Ordering::SeqCst);
        self.set_state(ConnectionState::Disconnected, "Disconnected");
        Ok(())
    }

    /// Check if connected to the daemon
    pub fn is_connected(&self) -> bool {
        self.connected.load(Ordering::SeqCst)
    }

    /// Attempt to reconnect if disconnected
    pub async fn ensure_connected(&self) -> Result<(), DaemonError> {
        if self.is_connected() {
            return Ok(());
        }

        // Try a ping first to check if we can connect
        if Self::test_connection(&self.socket_path) {
            self.register_terminal().await?;
        } else if self.reconnect_config.enabled {
            // Start reconnection loop in background
            self.start_reconnection_task();
        }

        Ok(())
    }

    /// Start a background reconnection task
    fn start_reconnection_task(&self) {
        let socket_path = self.socket_path.clone();
        let connected = self.connected.clone();
        let terminal_id = self.terminal_id.clone();
        let timeout = self.timeout;
        let config = self.reconnect_config.clone();
        let retry_count = self.retry_count.clone();
        let state_tx = self.state_tx.clone();
        let current_state = self.current_state.clone();

        tokio::spawn(async move {
            let mut delay = config.initial_delay;

            loop {
                let count = retry_count.load(Ordering::SeqCst);
                if config.max_retries > 0 && count >= config.max_retries {
                    let _ = state_tx.send(ConnectionStateEvent {
                        state: ConnectionState::Failed,
                        message: "Max retries exceeded".to_string(),
                        retry_count: count,
                    });
                    break;
                }

                {
                    let mut state = current_state.lock().unwrap();
                    *state = ConnectionState::Reconnecting;
                }
                let _ = state_tx.send(ConnectionStateEvent {
                    state: ConnectionState::Reconnecting,
                    message: format!("Reconnecting (attempt {})", count + 1),
                    retry_count: count,
                });

                // Try to connect
                if Self::test_connection(&socket_path) {
                    // Try to register
                    let request = DaemonRequest::RegisterTerminal {
                        terminal_id: terminal_id.clone(),
                        pid: std::process::id(),
                        tty: std::env::var("TTY").ok(),
                    };

                    let json = match request.to_json_line() {
                        Ok(j) => j,
                        Err(_) => continue,
                    };

                    let result = tokio::task::spawn_blocking({
                        let socket_path = socket_path.clone();
                        move || {
                            let stream = UnixStream::connect(&socket_path)?;
                            stream.set_read_timeout(Some(timeout))?;
                            stream.set_write_timeout(Some(timeout))?;

                            let mut stream = stream;
                            stream.write_all(json.as_bytes())?;

                            let mut reader = BufReader::new(&stream);
                            let mut response = String::new();
                            reader.read_line(&mut response)?;

                            Ok::<String, std::io::Error>(response)
                        }
                    })
                    .await;

                    if let Ok(Ok(response)) = result {
                        if let Ok(DaemonResponse::Success { .. }) =
                            DaemonResponse::from_json(&response)
                        {
                            connected.store(true, Ordering::SeqCst);
                            retry_count.store(0, Ordering::SeqCst);
                            {
                                let mut state = current_state.lock().unwrap();
                                *state = ConnectionState::Connected;
                            }
                            let _ = state_tx.send(ConnectionStateEvent {
                                state: ConnectionState::Connected,
                                message: "Reconnected successfully".to_string(),
                                retry_count: 0,
                            });
                            break;
                        }
                    }
                }

                retry_count.fetch_add(1, Ordering::SeqCst);
                tokio::time::sleep(delay).await;
                delay = Duration::from_secs_f64(
                    (delay.as_secs_f64() * config.backoff_multiplier)
                        .min(config.max_delay.as_secs_f64()),
                );
            }
        });
    }

    /// Execute an agent command through the daemon
    pub async fn execute_agent(
        &self,
        agent: &str,
        command: &str,
    ) -> Result<AgentResult, DaemonError> {
        self.ensure_connected().await?;

        let request = DaemonRequest::agent_execute(agent, command);

        match self.send_request(&request).await? {
            DaemonResponse::AgentResult {
                success,
                result,
                commands_executed,
                suggestions,
                error,
            } => Ok(AgentResult {
                success,
                result,
                commands_executed,
                suggestions,
                error,
            }),
            DaemonResponse::Error { message, .. } => Err(DaemonError::AgentError(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Query AI through the daemon (uses fine-tuned CX model)
    pub async fn query_ai(
        &self,
        query: &str,
        context: &TerminalContext,
    ) -> Result<AIResponse, DaemonError> {
        self.ensure_connected().await?;

        let mut ctx = context.clone();
        ctx.terminal_id = Some(self.terminal_id.clone());

        let request = DaemonRequest::AIQuery {
            query: query.to_string(),
            context: ctx,
            system_prompt: None,
            stream: false,
        };

        match self.send_request(&request).await? {
            DaemonResponse::AIResponse {
                content,
                model,
                tokens_used,
                cached,
            } => Ok(AIResponse {
                content,
                model,
                tokens_used,
                cached,
            }),
            DaemonResponse::Error { message, .. } => Err(DaemonError::AIError(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Query AI with streaming response
    pub async fn query_ai_stream(
        &self,
        query: &str,
        context: &TerminalContext,
        mut on_chunk: impl FnMut(String),
    ) -> Result<(), DaemonError> {
        self.ensure_connected().await?;

        let mut ctx = context.clone();
        ctx.terminal_id = Some(self.terminal_id.clone());

        let request = DaemonRequest::AIQuery {
            query: query.to_string(),
            context: ctx,
            system_prompt: None,
            stream: true,
        };

        let stream = self.connect_stream()?;
        let mut stream_writer = stream.try_clone().map_err(|e| {
            DaemonError::ConnectionFailed(format!("Failed to clone stream: {}", e))
        })?;

        // Send request
        let json = request.to_json_line()?;
        stream_writer
            .write_all(json.as_bytes())
            .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

        // Read streaming response
        let reader = BufReader::new(&stream);
        for line in reader.lines() {
            let line = line.map_err(|e| {
                // Mark as disconnected on read error
                self.connected.store(false, Ordering::SeqCst);
                self.set_state(ConnectionState::Disconnected, "Connection lost");
                DaemonError::ConnectionFailed(e.to_string())
            })?;

            match DaemonResponse::from_json(&line)? {
                DaemonResponse::AIStreamChunk { content, done } => {
                    on_chunk(content);
                    if done {
                        break;
                    }
                }
                DaemonResponse::Error { message, .. } => {
                    return Err(DaemonError::AIError(message));
                }
                _ => {}
            }
        }

        Ok(())
    }

    /// Query AI with a system prompt
    pub async fn query_ai_with_system(
        &self,
        query: &str,
        context: &TerminalContext,
        system_prompt: &str,
    ) -> Result<AIResponse, DaemonError> {
        self.ensure_connected().await?;

        let mut ctx = context.clone();
        ctx.terminal_id = Some(self.terminal_id.clone());

        let request = DaemonRequest::AIQuery {
            query: query.to_string(),
            context: ctx,
            system_prompt: Some(system_prompt.to_string()),
            stream: false,
        };

        match self.send_request(&request).await? {
            DaemonResponse::AIResponse {
                content,
                model,
                tokens_used,
                cached,
            } => Ok(AIResponse {
                content,
                model,
                tokens_used,
                cached,
            }),
            DaemonResponse::Error { message, .. } => Err(DaemonError::AIError(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Send command history for learning
    pub async fn learn_from_command(
        &self,
        command: &str,
        output: &str,
        exit_code: i32,
        duration_ms: u64,
        cwd: &str,
    ) -> Result<(), DaemonError> {
        // Don't block on learning - fire and forget
        if !self.is_connected() {
            return Ok(());
        }

        // Truncate output if too long
        let max_output_len = 10000;
        let truncated_output = if output.len() > max_output_len {
            format!("{}...[truncated]", &output[..max_output_len])
        } else {
            output.to_string()
        };

        let request = DaemonRequest::learn(command, &truncated_output, exit_code, duration_ms, cwd);

        // Fire and forget - don't wait for response
        let _ = self.send_request_no_wait(&request);
        Ok(())
    }

    /// Get context from daemon
    pub async fn get_context(
        &self,
        context_type: ContextType,
    ) -> Result<serde_json::Value, DaemonError> {
        self.ensure_connected().await?;

        let request = DaemonRequest::GetContext { context_type };

        match self.send_request(&request).await? {
            DaemonResponse::Context { data, .. } => Ok(data),
            DaemonResponse::Error { message, .. } => Err(DaemonError::NotFound(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Get system status from daemon
    pub async fn get_system_status(&self) -> Result<SystemInfo, DaemonError> {
        self.ensure_connected().await?;

        let request = DaemonRequest::GetContext {
            context_type: ContextType::System,
        };

        match self.send_request(&request).await? {
            DaemonResponse::Context { data, .. } => {
                // Parse system info from JSON
                Ok(SystemInfo {
                    os: data["os"].as_str().unwrap_or("unknown").to_string(),
                    kernel: data["kernel"].as_str().unwrap_or("unknown").to_string(),
                    hostname: data["hostname"].as_str().unwrap_or("unknown").to_string(),
                    uptime_secs: data["uptime_secs"].as_u64().unwrap_or(0),
                    memory_total: data["memory_total"].as_u64().unwrap_or(0),
                    memory_used: data["memory_used"].as_u64().unwrap_or(0),
                    cpu_count: data["cpu_count"].as_u64().unwrap_or(0) as u32,
                    load_average: data["load_average"]
                        .as_array()
                        .map(|a| {
                            a.iter()
                                .filter_map(|v| v.as_f64())
                                .collect::<Vec<_>>()
                        })
                        .unwrap_or_default(),
                })
            }
            DaemonResponse::Error { message, .. } => Err(DaemonError::NotFound(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// List available agents from daemon
    pub async fn list_agents(&self) -> Result<Vec<AgentInfo>, DaemonError> {
        self.ensure_connected().await?;

        let request = DaemonRequest::ListAgents;

        match self.send_request(&request).await? {
            DaemonResponse::AgentList { agents } => Ok(agents),
            DaemonResponse::Error { message, .. } => Err(DaemonError::NotFound(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Get daemon status
    pub async fn status(&self) -> Result<DaemonStatus, DaemonError> {
        let request = DaemonRequest::Status;

        match self.send_request(&request).await? {
            DaemonResponse::Status {
                version,
                uptime_secs,
                connected_terminals,
                ai_provider,
                learning_enabled,
                agents_available,
            } => Ok(DaemonStatus {
                version,
                uptime_secs,
                connected_terminals,
                ai_provider,
                learning_enabled,
                agents_available,
            }),
            DaemonResponse::Error { message, .. } => Err(DaemonError::NotAvailable(message)),
            _ => Err(DaemonError::Protocol("Unexpected response".to_string())),
        }
    }

    /// Run an agent task through the daemon
    pub async fn run_agent_task(
        &self,
        agent: &str,
        command: &str,
    ) -> Result<AgentResponse, DaemonError> {
        self.ensure_connected().await?;

        let result = self.execute_agent(agent, command).await?;

        Ok(AgentResponse {
            success: result.success,
            result: result.result,
            commands_executed: result.commands_executed,
            suggestions: result.suggestions,
            error: result.error,
        })
    }

    /// Send a request and wait for response
    async fn send_request(&self, request: &DaemonRequest) -> Result<DaemonResponse, DaemonError> {
        // Use synchronous IO wrapped in spawn_blocking for async
        let socket_path = self.socket_path.clone();
        let timeout = self.timeout;
        let json = request.to_json_line()?;
        let connected = self.connected.clone();

        let response = tokio::task::spawn_blocking(move || {
            let stream = UnixStream::connect(&socket_path).map_err(|e| {
                connected.store(false, Ordering::SeqCst);
                DaemonError::NotAvailable(format!("{}: {}", socket_path.display(), e))
            })?;

            stream
                .set_read_timeout(Some(timeout))
                .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;
            stream
                .set_write_timeout(Some(timeout))
                .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

            let mut stream = stream;
            stream
                .write_all(json.as_bytes())
                .map_err(|e| {
                    connected.store(false, Ordering::SeqCst);
                    DaemonError::ConnectionFailed(e.to_string())
                })?;

            let mut reader = BufReader::new(&stream);
            let mut response = String::new();
            reader
                .read_line(&mut response)
                .map_err(|e| {
                    connected.store(false, Ordering::SeqCst);
                    DaemonError::ConnectionFailed(e.to_string())
                })?;

            DaemonResponse::from_json(&response)
        })
        .await
        .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))??;

        // Check if response indicates we should reconnect
        if response.is_error() {
            if let Some(msg) = response.error_message() {
                if msg.contains("not registered") || msg.contains("unknown terminal") {
                    self.connected.store(false, Ordering::SeqCst);
                    self.set_state(ConnectionState::Disconnected, "Session expired");
                }
            }
        }

        Ok(response)
    }

    /// Send a request without waiting for response
    fn send_request_no_wait(&self, request: &DaemonRequest) -> Result<(), DaemonError> {
        let json = request.to_json_line()?;
        let socket_path = self.socket_path.clone();

        // Spawn a background task to send
        std::thread::spawn(move || {
            if let Ok(mut stream) = UnixStream::connect(&socket_path) {
                let _ = stream.set_write_timeout(Some(Duration::from_secs(1)));
                let _ = stream.write_all(json.as_bytes());
            }
        });

        Ok(())
    }

    /// Connect to daemon and return the stream
    fn connect_stream(&self) -> Result<UnixStream, DaemonError> {
        let stream = UnixStream::connect(&self.socket_path).map_err(|e| {
            self.connected.store(false, Ordering::SeqCst);
            DaemonError::NotAvailable(format!("{}: {}", self.socket_path.display(), e))
        })?;

        stream
            .set_read_timeout(Some(self.timeout))
            .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;
        stream
            .set_write_timeout(Some(self.timeout))
            .map_err(|e| DaemonError::ConnectionFailed(e.to_string()))?;

        Ok(stream)
    }

    /// Get terminal ID
    pub fn terminal_id(&self) -> &str {
        &self.terminal_id
    }

    /// Get socket path
    pub fn socket_path(&self) -> &PathBuf {
        &self.socket_path
    }

    /// Get retry count
    pub fn retry_count(&self) -> u32 {
        self.retry_count.load(Ordering::SeqCst)
    }
}

impl Default for CXDaemonClient {
    fn default() -> Self {
        Self::new()
    }
}

impl Drop for CXDaemonClient {
    fn drop(&mut self) {
        if self.connected.load(Ordering::SeqCst) {
            // Try to unregister on drop
            let request = DaemonRequest::UnregisterTerminal {
                terminal_id: self.terminal_id.clone(),
            };
            let _ = self.send_request_no_wait(&request);
        }
    }
}

/// Result from agent execution
#[derive(Debug, Clone)]
pub struct AgentResult {
    pub success: bool,
    pub result: String,
    pub commands_executed: Vec<String>,
    pub suggestions: Vec<String>,
    pub error: Option<String>,
}

/// Response from AI query
#[derive(Debug, Clone)]
pub struct AIResponse {
    pub content: String,
    pub model: String,
    pub tokens_used: Option<u32>,
    pub cached: bool,
}

/// Response from agent task
#[derive(Debug, Clone)]
pub struct AgentResponse {
    pub success: bool,
    pub result: String,
    pub commands_executed: Vec<String>,
    pub suggestions: Vec<String>,
    pub error: Option<String>,
}

/// Daemon status information
#[derive(Debug, Clone)]
pub struct DaemonStatus {
    pub version: String,
    pub uptime_secs: u64,
    pub connected_terminals: u32,
    pub ai_provider: String,
    pub learning_enabled: bool,
    pub agents_available: Vec<String>,
}

/// System information from daemon
#[derive(Debug, Clone)]
pub struct SystemInfo {
    pub os: String,
    pub kernel: String,
    pub hostname: String,
    pub uptime_secs: u64,
    pub memory_total: u64,
    pub memory_used: u64,
    pub cpu_count: u32,
    pub load_average: Vec<f64>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_client_creation() {
        let client = CXDaemonClient::new();
        assert!(!client.terminal_id.is_empty());
        assert_eq!(client.connection_state(), ConnectionState::Disconnected);
    }

    #[test]
    fn test_find_socket_path() {
        let path = CXDaemonClient::find_socket_path();
        // Should always return some path
        assert!(!path.to_string_lossy().is_empty());
    }

    #[test]
    fn test_reconnect_config() {
        let config = ReconnectConfig::default();
        assert!(config.enabled);
        assert_eq!(config.max_retries, 10);
        assert_eq!(config.backoff_multiplier, 2.0);
    }

    #[tokio::test]
    async fn test_is_available() {
        // This will typically be false in test environment
        let _ = CXDaemonClient::is_available();
    }

    #[tokio::test]
    async fn test_state_subscription() {
        let client = CXDaemonClient::new();
        let mut rx = client.subscribe_state_changes();

        // Initially disconnected
        assert_eq!(client.connection_state(), ConnectionState::Disconnected);

        // State changes would be received here if connection was attempted
        // For now, just verify subscription works
        drop(rx);
    }
}
