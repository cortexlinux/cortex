//! Audio Capture for Voice Input
//!
//! Provides audio capture functionality for voice commands using cpal:
//! - Push-to-talk recording
//! - Voice Activity Detection (VAD)
//! - Audio format: 16kHz mono PCM

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, Host, Stream, StreamConfig};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

/// Audio capture configuration
#[derive(Debug, Clone)]
pub struct AudioConfig {
    /// Sample rate in Hz (default: 16000)
    pub sample_rate: u32,

    /// Number of channels (default: 1 - mono)
    pub channels: u16,

    /// Buffer size in samples
    pub buffer_size: usize,
}

impl Default for AudioConfig {
    fn default() -> Self {
        Self {
            sample_rate: 16000,
            channels: 1,
            buffer_size: 1024,
        }
    }
}

/// Audio capture state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CaptureState {
    /// Not initialized
    Uninitialized,
    /// Ready to record
    Ready,
    /// Currently recording
    Recording,
    /// Stopped, audio available
    Stopped,
    /// Error state
    Error,
}

/// Audio capture errors
#[derive(Debug, thiserror::Error)]
pub enum CaptureError {
    #[error("Failed to initialize audio device: {0}")]
    DeviceInit(String),

    #[error("Failed to start recording: {0}")]
    StartRecording(String),

    #[error("Failed to stop recording: {0}")]
    StopRecording(String),

    #[error("No audio device available")]
    NoDevice,

    #[error("Audio capture not initialized")]
    NotInitialized,

    #[error("Audio capture already running")]
    AlreadyRunning,

    #[error("Buffer overflow")]
    BufferOverflow,

    #[error("Stream error: {0}")]
    StreamError(String),

    #[error("Config error: {0}")]
    ConfigError(String),
}

/// Voice Activity Detector
///
/// Simple energy-based VAD to detect speech.
pub struct VoiceActivityDetector {
    /// Threshold for detecting voice activity
    threshold: f32,

    /// Minimum consecutive frames of activity to trigger
    min_active_frames: usize,

    /// Minimum consecutive frames of silence to stop
    min_silent_frames: usize,

    /// Current consecutive active frames
    active_frame_count: usize,

    /// Current consecutive silent frames
    silent_frame_count: usize,

    /// Whether speech is currently detected
    is_active: bool,

    /// Energy history for adaptive thresholding
    energy_history: Vec<f32>,

    /// Maximum history size
    history_size: usize,
}

impl VoiceActivityDetector {
    /// Create a new VAD with the given energy threshold
    pub fn new(threshold: f32) -> Self {
        Self {
            threshold,
            min_active_frames: 3,
            min_silent_frames: 10,
            active_frame_count: 0,
            silent_frame_count: 0,
            is_active: false,
            energy_history: Vec::with_capacity(100),
            history_size: 100,
        }
    }

    /// Process a frame of audio and update VAD state
    ///
    /// Returns true if voice activity is detected.
    pub fn process(&mut self, samples: &[i16]) -> bool {
        let energy = self.compute_energy(samples);

        // Update energy history
        self.energy_history.push(energy);
        if self.energy_history.len() > self.history_size {
            self.energy_history.remove(0);
        }

        // Use adaptive threshold if we have enough history
        let threshold = if self.energy_history.len() >= 20 {
            self.compute_adaptive_threshold()
        } else {
            self.threshold
        };

        if energy > threshold {
            self.active_frame_count += 1;
            self.silent_frame_count = 0;

            if self.active_frame_count >= self.min_active_frames {
                self.is_active = true;
            }
        } else {
            self.silent_frame_count += 1;
            self.active_frame_count = 0;

            if self.silent_frame_count >= self.min_silent_frames {
                self.is_active = false;
            }
        }

        self.is_active
    }

    /// Compute the energy (RMS) of a frame
    fn compute_energy(&self, samples: &[i16]) -> f32 {
        if samples.is_empty() {
            return 0.0;
        }

        let sum_squares: f64 = samples.iter().map(|&s| (s as f64).powi(2)).sum();
        let rms = (sum_squares / samples.len() as f64).sqrt();

        // Normalize to 0.0 - 1.0 range
        (rms / 32768.0) as f32
    }

    /// Compute adaptive threshold based on energy history
    fn compute_adaptive_threshold(&self) -> f32 {
        if self.energy_history.is_empty() {
            return self.threshold;
        }

        // Use the 25th percentile of recent energy as noise floor
        let mut sorted = self.energy_history.clone();
        sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let percentile_idx = (sorted.len() as f32 * 0.25) as usize;
        let noise_floor = sorted.get(percentile_idx).copied().unwrap_or(0.0);

        // Threshold is noise floor + configured sensitivity
        (noise_floor + self.threshold).min(1.0)
    }

    /// Reset VAD state
    pub fn reset(&mut self) {
        self.active_frame_count = 0;
        self.silent_frame_count = 0;
        self.is_active = false;
        self.energy_history.clear();
    }

    /// Check if currently detecting voice activity
    pub fn is_active(&self) -> bool {
        self.is_active
    }
}

/// Audio capture device using cpal
///
/// Cross-platform audio capture for voice input.
pub struct AudioCapture {
    /// Configuration
    config: AudioConfig,

    /// Current state
    state: CaptureState,

    /// Recording flag
    is_recording: Arc<AtomicBool>,

    /// Audio buffer
    buffer: Arc<Mutex<Vec<i16>>>,

    /// Voice activity detector
    vad: Option<VoiceActivityDetector>,

    /// cpal host
    #[allow(dead_code)]
    host: Host,

    /// Input device
    device: Device,

    /// Stream configuration
    stream_config: StreamConfig,

    /// Active stream (only present while recording)
    stream: Option<Stream>,
}

impl AudioCapture {
    /// Create a new audio capture device
    pub fn new(config: AudioConfig) -> Result<Self, CaptureError> {
        let host = cpal::default_host();

        let device = host
            .default_input_device()
            .ok_or(CaptureError::NoDevice)?;

        let device_name = device.name().unwrap_or_else(|_| "Unknown".to_string());
        log::info!("Using audio input device: {}", device_name);

        // Get supported config and try to match our requirements
        let supported_configs = device
            .supported_input_configs()
            .map_err(|e| CaptureError::ConfigError(e.to_string()))?;

        // Find a config that supports our sample rate
        let mut best_config = None;
        for cfg in supported_configs {
            if cfg.channels() == config.channels
                && cfg.min_sample_rate().0 <= config.sample_rate
                && cfg.max_sample_rate().0 >= config.sample_rate
            {
                best_config = Some(cfg.with_sample_rate(cpal::SampleRate(config.sample_rate)));
                break;
            }
        }

        // Fall back to default config if no exact match
        let supported_config = match best_config {
            Some(cfg) => cfg,
            None => {
                let default_config = device
                    .default_input_config()
                    .map_err(|e| CaptureError::ConfigError(e.to_string()))?;
                log::warn!(
                    "Requested config not supported, using device default: {:?}",
                    default_config
                );
                default_config
            }
        };

        let stream_config: StreamConfig = supported_config.into();

        log::info!(
            "Audio capture configured: {}Hz, {} channels",
            stream_config.sample_rate.0,
            stream_config.channels
        );

        Ok(Self {
            config,
            state: CaptureState::Ready,
            is_recording: Arc::new(AtomicBool::new(false)),
            buffer: Arc::new(Mutex::new(Vec::new())),
            vad: None,
            host,
            device,
            stream_config,
            stream: None,
        })
    }

    /// List available input devices
    pub fn list_devices() -> Result<Vec<String>, CaptureError> {
        let host = cpal::default_host();
        let devices = host
            .input_devices()
            .map_err(|e| CaptureError::DeviceInit(e.to_string()))?;

        Ok(devices
            .filter_map(|d| d.name().ok())
            .collect())
    }

    /// Enable voice activity detection
    pub fn enable_vad(&mut self, threshold: f32) {
        self.vad = Some(VoiceActivityDetector::new(threshold));
    }

    /// Disable voice activity detection
    pub fn disable_vad(&mut self) {
        self.vad = None;
    }

    /// Start recording
    pub fn start(&mut self) -> Result<(), CaptureError> {
        if self.state == CaptureState::Uninitialized {
            return Err(CaptureError::NotInitialized);
        }

        if self.is_recording.load(Ordering::SeqCst) {
            return Err(CaptureError::AlreadyRunning);
        }

        // Clear the buffer
        if let Ok(mut buffer) = self.buffer.lock() {
            buffer.clear();
        }

        // Reset VAD state
        if let Some(vad) = &mut self.vad {
            vad.reset();
        }

        // Create the stream
        let is_recording = self.is_recording.clone();
        let buffer = self.buffer.clone();
        let stream_config = self.stream_config.clone();

        let stream = self
            .device
            .build_input_stream(
                &stream_config,
                move |data: &[f32], _: &cpal::InputCallbackInfo| {
                    if is_recording.load(Ordering::SeqCst) {
                        // Convert f32 samples to i16
                        let samples: Vec<i16> = data
                            .iter()
                            .map(|&s| (s * 32767.0).clamp(-32768.0, 32767.0) as i16)
                            .collect();

                        if let Ok(mut buf) = buffer.lock() {
                            buf.extend_from_slice(&samples);
                        }
                    }
                },
                |err| log::error!("Audio capture error: {}", err),
                None,
            )
            .map_err(|e| CaptureError::StartRecording(e.to_string()))?;

        stream
            .play()
            .map_err(|e| CaptureError::StartRecording(e.to_string()))?;

        self.stream = Some(stream);
        self.is_recording.store(true, Ordering::SeqCst);
        self.state = CaptureState::Recording;

        log::info!("Audio capture started");

        Ok(())
    }

    /// Stop recording and return captured audio
    pub fn stop(&mut self) -> Result<Vec<i16>, CaptureError> {
        if !self.is_recording.load(Ordering::SeqCst) {
            return Ok(Vec::new());
        }

        self.is_recording.store(false, Ordering::SeqCst);
        self.state = CaptureState::Stopped;

        // Stop and drop the stream
        if let Some(stream) = self.stream.take() {
            let _ = stream.pause();
            drop(stream);
        }

        let buffer = self
            .buffer
            .lock()
            .map_err(|_| CaptureError::StopRecording("Failed to lock buffer".to_string()))?
            .clone();

        log::info!("Audio capture stopped, {} samples captured", buffer.len());

        Ok(buffer)
    }

    /// Get current state
    pub fn state(&self) -> CaptureState {
        self.state
    }

    /// Check if currently recording
    pub fn is_recording(&self) -> bool {
        self.is_recording.load(Ordering::SeqCst)
    }

    /// Get configuration
    pub fn config(&self) -> &AudioConfig {
        &self.config
    }

    /// Get actual stream sample rate
    pub fn actual_sample_rate(&self) -> u32 {
        self.stream_config.sample_rate.0
    }

    /// Get actual channel count
    pub fn actual_channels(&self) -> u16 {
        self.stream_config.channels
    }

    /// Process buffer with VAD and return voice segments
    pub fn get_voice_segments(&mut self) -> Vec<Vec<i16>> {
        let vad = match &mut self.vad {
            Some(v) => v,
            None => return Vec::new(),
        };

        let buffer = match self.buffer.lock() {
            Ok(b) => b.clone(),
            Err(_) => return Vec::new(),
        };

        if buffer.is_empty() {
            return Vec::new();
        }

        let frame_size = self.config.buffer_size;
        let mut segments = Vec::new();
        let mut current_segment = Vec::new();
        let mut was_active = false;

        for chunk in buffer.chunks(frame_size) {
            let is_active = vad.process(chunk);

            if is_active {
                current_segment.extend_from_slice(chunk);
                was_active = true;
            } else if was_active && !current_segment.is_empty() {
                // End of voice segment
                segments.push(std::mem::take(&mut current_segment));
                was_active = false;
            }
        }

        // Include any remaining active segment
        if !current_segment.is_empty() {
            segments.push(current_segment);
        }

        segments
    }
}

// Stream is not Send/Sync safe, so we need this for the struct
// The stream is only accessed on the main thread
unsafe impl Send for AudioCapture {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vad_energy() {
        let vad = VoiceActivityDetector::new(0.05);

        // Silent samples
        let silent = vec![0i16; 100];
        let energy = vad.compute_energy(&silent);
        assert!(energy < 0.001);

        // Loud samples
        let loud: Vec<i16> = (0..100).map(|i| ((i as f32 / 100.0 * 32767.0) as i16)).collect();
        let energy = vad.compute_energy(&loud);
        assert!(energy > 0.3);
    }

    #[test]
    fn test_vad_detection() {
        let mut vad = VoiceActivityDetector::new(0.05);

        // Silent frames
        let silent = vec![0i16; 1024];
        for _ in 0..20 {
            vad.process(&silent);
        }
        assert!(!vad.is_active());

        // Loud frames should trigger activity
        let loud: Vec<i16> = (0..1024)
            .map(|i| ((i as f32 / 1024.0 * 32767.0 * 0.5) as i16))
            .collect();
        for _ in 0..5 {
            vad.process(&loud);
        }
        assert!(vad.is_active());
    }

    #[test]
    fn test_audio_config_default() {
        let config = AudioConfig::default();
        assert_eq!(config.sample_rate, 16000);
        assert_eq!(config.channels, 1);
        assert_eq!(config.buffer_size, 1024);
    }
}
