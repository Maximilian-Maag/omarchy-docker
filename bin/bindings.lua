-- Hyprland keybindings added by omarchy-docker.
-- Sourced from hyprland.lua by install.sh (require("hypr.docker-bindings")).
--
-- Opens the Docker container view in a floating terminal. The app-id
-- org.omarchy.* makes Omarchy auto-float the window.

hl.unbind("SUPER + SHIFT + ALT + D")
o.bind("SUPER + SHIFT + ALT + D", "Docker containers",
       "xdg-terminal-exec --app-id=org.omarchy.docker --title='Docker' -- "
       .. "omarchy-docker list")
