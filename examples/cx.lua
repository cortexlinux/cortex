-- CX Terminal Configuration
-- Place this file at ~/.config/cx/cx.lua or ~/.cx.lua
--
-- CX Terminal - AI-native terminal for CX Linux
-- https://cxlinux.ai

local cx = require 'cx'

-- Create config builder
local config = cx.config_builder()

-------------------------------------------------------------------------------
-- APPEARANCE
-------------------------------------------------------------------------------

-- Color scheme (CX Dark is the default)
-- Use "CX Light" for a light theme
config.color_scheme = "CX Dark"

-- Font settings - System fonts FIRST to avoid "Unable to load font" errors
-- macOS: Menlo and Monaco are always available
-- Linux: DejaVu Sans Mono is typically available
-- Then fall back to optional fonts if installed
config.font = cx.font_with_fallback({
    "Menlo",             -- macOS system font (always present)
    "Monaco",            -- macOS classic (always present)
    "DejaVu Sans Mono",  -- Linux fallback
    "Consolas",          -- Windows fallback
    "JetBrains Mono",    -- If installed (recommended)
    "Fira Code",         -- If installed
})
config.font_size = 14.0

-- Enable ligatures if using a font that supports them
config.harfbuzz_features = {
    "calt=1",  -- Contextual alternates
    "liga=1",  -- Standard ligatures
}

-- Window appearance
config.window_background_opacity = 0.95
config.window_decorations = "RESIZE"
config.window_padding = {
    left = 12,
    right = 12,
    top = 12,
    bottom = 12,
}

-- Tab bar
config.hide_tab_bar_if_only_one_tab = false
config.tab_bar_at_bottom = false
config.use_fancy_tab_bar = true

-- Cursor
config.default_cursor_style = "SteadyBlock"
config.cursor_blink_rate = 500

-------------------------------------------------------------------------------
-- STATUS BAR - Enhanced AI Ready + Git Integration
-------------------------------------------------------------------------------

config.status_update_interval = 2000

-- AI Provider Status Detection
local function get_ai_status()
    -- Check for API keys and determine AI provider status
    local claude_key = os.getenv("ANTHROPIC_API_KEY")
    local openai_key = os.getenv("OPENAI_API_KEY")
    local ollama_host = os.getenv("OLLAMA_HOST")

    if claude_key and claude_key ~= "" then
        return { icon = "🤖", text = "Claude", color = "#00D9FF" }
    elseif openai_key and openai_key ~= "" then
        return { icon = "🧠", text = "OpenAI", color = "#00D9FF" }
    elseif ollama_host and ollama_host ~= "" then
        return { icon = "🏠", text = "Local AI", color = "#FFB86C" }
    else
        -- Check if ollama is running locally
        local ollama_check = os.execute("curl -s http://localhost:11434/api/tags >/dev/null 2>&1")
        if ollama_check == 0 then
            return { icon = "🏠", text = "Ollama", color = "#FFB86C" }
        end
    end

    return { icon = "💤", text = "No AI", color = "#6272A4" }
end

-- System stats for enhanced status bar
local function get_system_stats()
    local stats = {}

    -- Get current time
    stats.time = os.date("%H:%M")

    -- Try to get CPU usage (macOS/Linux)
    local cpu_success, cpu_result = pcall(function()
        if os.execute("command -v top >/dev/null 2>&1") == 0 then
            local handle = io.popen("top -l 1 -n 0 2>/dev/null | grep 'CPU usage' | awk '{print $3}' | sed 's/%//'")
            if handle then
                local result = handle:read("*l")
                handle:close()
                if result and result ~= "" then
                    return tonumber(result)
                end
            end
        end
        return nil
    end)

    if cpu_success and cpu_result then
        stats.cpu = math.floor(cpu_result)
    end

    return stats
end

cx.on('update-status', function(window, pane)
    local cells = {}

    -- Left status: Enhanced working directory with CX branding
    local cwd_uri = pane:get_current_working_dir()
    if cwd_uri then
        local cwd = cwd_uri.file_path or ""
        -- Shorten home directory
        local home = os.getenv("HOME") or ""
        if home ~= "" and cwd:sub(1, #home) == home then
            cwd = "~" .. cwd:sub(#home + 1)
        end

        -- CX Terminal brand indicator
        table.insert(cells, { Foreground = { Color = "#00FFFF" } })
        table.insert(cells, { Text = " CX " })
        table.insert(cells, { Foreground = { Color = "#44475A" } })
        table.insert(cells, { Text = "│" })
        table.insert(cells, { Foreground = { Color = "#6272A4" } })
        table.insert(cells, { Text = " 📁 " .. cwd .. " " })
    end

    window:set_left_status(cx.format(cells))

    -- Right status: Enhanced with system stats + AI status
    local right_cells = {}
    local stats = get_system_stats()

    -- System time
    table.insert(right_cells, { Foreground = { Color = "#8BE9FD" } })
    table.insert(right_cells, { Text = " 🕐 " .. stats.time })

    -- CPU usage if available
    if stats.cpu then
        table.insert(right_cells, { Text = " " })
        table.insert(right_cells, { Foreground = { Color = "#44475A" } })
        table.insert(right_cells, { Text = "│" })

        local cpu_color = "#50FA7B" -- Green
        if stats.cpu > 80 then
            cpu_color = "#FF5555" -- Red
        elseif stats.cpu > 60 then
            cpu_color = "#F1FA8C" -- Yellow
        end

        table.insert(right_cells, { Foreground = { Color = cpu_color } })
        table.insert(right_cells, { Text = " 💻 " .. stats.cpu .. "%" })
    end

    -- Git branch indicator (enhanced)
    if cwd_uri then
        local success, stdout = pcall(function()
            local handle = io.popen('git -C "' .. (cwd_uri.file_path or ".") .. '" branch --show-current 2>/dev/null')
            if handle then
                local result = handle:read("*l")
                handle:close()
                return result
            end
            return nil
        end)

        if success and stdout and stdout ~= "" then
            -- Check if dirty
            local dirty_handle = io.popen('git -C "' .. (cwd_uri.file_path or ".") .. '" status --porcelain 2>/dev/null | head -1')
            local is_dirty = false
            if dirty_handle then
                local dirty_result = dirty_handle:read("*l")
                dirty_handle:close()
                is_dirty = dirty_result and dirty_result ~= ""
            end

            table.insert(right_cells, { Text = " " })
            table.insert(right_cells, { Foreground = { Color = "#44475A" } })
            table.insert(right_cells, { Text = "│" })
            table.insert(right_cells, { Foreground = { Color = "#50FA7B" } })
            table.insert(right_cells, { Text = " ⎇ " .. stdout })
            if is_dirty then
                table.insert(right_cells, { Foreground = { Color = "#F1FA8C" } })
                table.insert(right_cells, { Text = " ●" })
            end
        end
    end

    -- Enhanced AI Status indicator with dynamic detection
    local ai_status = get_ai_status()
    table.insert(right_cells, { Text = " " })
    table.insert(right_cells, { Foreground = { Color = "#44475A" } })
    table.insert(right_cells, { Text = "│" })
    table.insert(right_cells, { Foreground = { Color = ai_status.color } })
    table.insert(right_cells, { Text = " " .. ai_status.icon .. " " .. ai_status.text })

    -- Keyboard shortcut hint
    table.insert(right_cells, { Text = " " })
    table.insert(right_cells, { Foreground = { Color = "#44475A" } })
    table.insert(right_cells, { Text = "│" })
    table.insert(right_cells, { Foreground = { Color = "#6272A4" } })
    table.insert(right_cells, { Text = " ⌨️ ^Space " })

    window:set_right_status(cx.format(right_cells))
end)

-------------------------------------------------------------------------------
-- TERMINAL BEHAVIOR
-------------------------------------------------------------------------------

-- Scrollback
config.scrollback_lines = 50000

-- Bell
config.audible_bell = "Disabled"
config.visual_bell = {
    fade_in_function = "EaseIn",
    fade_in_duration_ms = 50,
    fade_out_function = "EaseOut",
    fade_out_duration_ms = 50,
}

-- Copy/paste
config.selection_word_boundary = " \t\n{}[]()\"'`,;:"

-------------------------------------------------------------------------------
-- KEY BINDINGS
-------------------------------------------------------------------------------

config.keys = {
    -- AI Integration
    { key = "Space", mods = "CTRL", action = cx.action.ShowLauncherArgs { flags = "COMMANDS" } },
    { key = "f", mods = "CTRL|SHIFT", action = cx.action.SendString("cx fix-last-error\n") },
    { key = "e", mods = "CTRL|SHIFT", action = cx.action.SendString("cx explain\n") },

    -- Pane management
    { key = "d", mods = "CMD", action = cx.action.SplitHorizontal { domain = "CurrentPaneDomain" } },
    { key = "d", mods = "CMD|SHIFT", action = cx.action.SplitVertical { domain = "CurrentPaneDomain" } },
    { key = "w", mods = "CMD|SHIFT", action = cx.action.CloseCurrentPane { confirm = true } },

    -- Pane navigation
    { key = "LeftArrow", mods = "CMD|ALT", action = cx.action.ActivatePaneDirection "Left" },
    { key = "RightArrow", mods = "CMD|ALT", action = cx.action.ActivatePaneDirection "Right" },
    { key = "UpArrow", mods = "CMD|ALT", action = cx.action.ActivatePaneDirection "Up" },
    { key = "DownArrow", mods = "CMD|ALT", action = cx.action.ActivatePaneDirection "Down" },
    { key = "h", mods = "CMD|ALT", action = cx.action.ActivatePaneDirection "Left" },
    { key = "l", mods = "CMD|ALT", action = cx.action.ActivatePaneDirection "Right" },
    { key = "k", mods = "CMD|ALT", action = cx.action.ActivatePaneDirection "Up" },
    { key = "j", mods = "CMD|ALT", action = cx.action.ActivatePaneDirection "Down" },

    -- Tab management
    { key = "t", mods = "CMD", action = cx.action.SpawnTab "CurrentPaneDomain" },
    { key = "w", mods = "CMD", action = cx.action.CloseCurrentTab { confirm = true } },
    { key = "[", mods = "CMD|SHIFT", action = cx.action.ActivateTabRelative(-1) },
    { key = "]", mods = "CMD|SHIFT", action = cx.action.ActivateTabRelative(1) },
    { key = "1", mods = "CMD", action = cx.action.ActivateTab(0) },
    { key = "2", mods = "CMD", action = cx.action.ActivateTab(1) },
    { key = "3", mods = "CMD", action = cx.action.ActivateTab(2) },
    { key = "4", mods = "CMD", action = cx.action.ActivateTab(3) },
    { key = "5", mods = "CMD", action = cx.action.ActivateTab(4) },
    { key = "6", mods = "CMD", action = cx.action.ActivateTab(5) },
    { key = "7", mods = "CMD", action = cx.action.ActivateTab(6) },
    { key = "8", mods = "CMD", action = cx.action.ActivateTab(7) },
    { key = "9", mods = "CMD", action = cx.action.ActivateTab(8) },

    -- Font size
    { key = "=", mods = "CMD", action = cx.action.IncreaseFontSize },
    { key = "-", mods = "CMD", action = cx.action.DecreaseFontSize },
    { key = "0", mods = "CMD", action = cx.action.ResetFontSize },

    -- Utilities
    { key = "p", mods = "CMD|SHIFT", action = cx.action.ActivateCommandPalette },
    { key = "f", mods = "CMD", action = cx.action.Search "CurrentSelectionOrEmptyString" },
    { key = "k", mods = "CMD", action = cx.action.ClearScrollback "ScrollbackAndViewport" },
    { key = "Enter", mods = "CMD", action = cx.action.ToggleFullScreen },
    { key = "r", mods = "CMD|SHIFT", action = cx.action.ReloadConfiguration },
}

-------------------------------------------------------------------------------
-- SESSION PERSISTENCE
-------------------------------------------------------------------------------

config.unix_domains = {
    { name = "cx-session" },
}

-------------------------------------------------------------------------------
-- AI INTEGRATION
-- Requires: ANTHROPIC_API_KEY or OLLAMA_HOST environment variable
-------------------------------------------------------------------------------

-- AI panel toggle: Ctrl+Space
-- Fix last error: Ctrl+Shift+F
-- Explain output: Ctrl+Shift+E

-- For Claude API:
-- export ANTHROPIC_API_KEY="your-api-key"

-- For local Ollama:
-- export OLLAMA_HOST="http://localhost:11434"
-- export OLLAMA_MODEL="llama3"

-------------------------------------------------------------------------------
-- SHELL INTEGRATION
-- Source the shell integration script in your shell config
-------------------------------------------------------------------------------

-- Bash: source /usr/share/cx-terminal/shell-integration/cx.bash
-- Zsh:  source /usr/share/cx-terminal/shell-integration/cx.zsh
-- Fish: source /usr/share/cx-terminal/shell-integration/cx.fish

return config
