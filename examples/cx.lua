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

-- Font settings - Fira Code with full ligatures
config.font = cx.font_with_fallback({
    "Fira Code",
    "JetBrains Mono",
    "Cascadia Code",
    "Menlo",
})
config.font_size = 14.0

-- Enable Fira Code ligatures and stylistic sets
config.harfbuzz_features = {
    "calt=1",  -- Contextual alternates
    "liga=1",  -- Standard ligatures
    "ss01=1",  -- r with serifs
    "ss02=1",  -- <= >= with horizontal bar
    "ss07=1",  -- ~= != with proper glyphs
    "zero=1",  -- Slashed zero
}

-- Window appearance
config.window_background_opacity = 0.98
config.window_decorations = "RESIZE"
config.window_padding = {
    left = 12,
    right = 12,
    top = 12,
    bottom = 12,
}

-- Tab bar
config.hide_tab_bar_if_only_one_tab = true
config.tab_bar_at_bottom = false
config.use_fancy_tab_bar = true

-- Cursor
config.default_cursor_style = "SteadyBlock"
config.cursor_blink_rate = 500

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
    -- Pane management
    { key = "d", mods = "CTRL|SHIFT", action = cx.action.SplitHorizontal { domain = "CurrentPaneDomain" } },
    { key = "e", mods = "CTRL|SHIFT", action = cx.action.SplitVertical { domain = "CurrentPaneDomain" } },
    { key = "w", mods = "CTRL|SHIFT", action = cx.action.CloseCurrentPane { confirm = true } },

    -- Pane navigation
    { key = "LeftArrow", mods = "CTRL|SHIFT", action = cx.action.ActivatePaneDirection "Left" },
    { key = "RightArrow", mods = "CTRL|SHIFT", action = cx.action.ActivatePaneDirection "Right" },
    { key = "UpArrow", mods = "CTRL|SHIFT", action = cx.action.ActivatePaneDirection "Up" },
    { key = "DownArrow", mods = "CTRL|SHIFT", action = cx.action.ActivatePaneDirection "Down" },

    -- Tab management
    { key = "t", mods = "CTRL|SHIFT", action = cx.action.SpawnTab "CurrentPaneDomain" },
    { key = "Tab", mods = "CTRL", action = cx.action.ActivateTabRelative(1) },
    { key = "Tab", mods = "CTRL|SHIFT", action = cx.action.ActivateTabRelative(-1) },

    -- Font size
    { key = "+", mods = "CTRL", action = cx.action.IncreaseFontSize },
    { key = "-", mods = "CTRL", action = cx.action.DecreaseFontSize },
    { key = "0", mods = "CTRL", action = cx.action.ResetFontSize },

    -- Command palette
    { key = "p", mods = "CTRL|SHIFT", action = cx.action.ActivateCommandPalette },
}

-------------------------------------------------------------------------------
-- AI INTEGRATION
-- Requires: ANTHROPIC_API_KEY or OLLAMA_HOST environment variable
-------------------------------------------------------------------------------

-- AI panel toggle: Ctrl+Space (default)
-- Explain selection: Ctrl+Shift+E
-- Suggest commands: Ctrl+Shift+S

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
