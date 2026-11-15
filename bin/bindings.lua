-- Hyprland keybindings added by omarchy-docker.
-- Sourced from hyprland.lua by install.sh (require("hypr.docker-bindings")).
--
-- Opens the Docker container view in a floating terminal. The app-id
-- org.omarchy.* makes Omarchy auto-float the window.
--
-- This file is a TEMPLATE: the placeholder below is substituted with
-- config/docker.json's "keybinding" value by `omarchy-docker bindings` (run by
-- install.sh), so editing the config changes what gets installed.

hl.unbind("__KEYBINDING__")
o.bind("__KEYBINDING__", "Docker containers",
       "xdg-terminal-exec --app-id=org.omarchy.docker --title='Docker' -- "
       .. "omarchy-docker list")
