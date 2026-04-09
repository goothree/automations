# Workspace keybindings

VS Code does not load `keybindings.json` from the workspace. To use **Cmd+Shift+D** to insert the current date in this project, add the following to your **user** keybindings:

1. **Cmd+Shift+P** → "Open Keyboard Shortcuts (JSON)"
2. Add this entry (so the shortcut only applies in this workspace):

```json
{
  "key": "cmd+shift+d",
  "command": "editor.action.insertSnippet",
  "when": "resourceDirname =~ /care\\.ai/",
  "args": {
    "snippet": "${CURRENT_YEAR}-${CURRENT_MONTH}-${CURRENT_DAY}"
  }
}
```

**Alternative:** In any file in this workspace, type `date` and choose the "Insert current date (YYYY-MM-DD)" snippet from the suggestion list.
