# VHS tape for safaribooks CLI demo
# Install VHS: https://github.com/charmbracelet/vhs
# Run: vhs assets/readme/demo.tape

Output assets/readme/demo.gif

Set Width 800
Set Height 600
Set Theme "Dracula"
Set FontSize 14
Set Padding 20
Set TypingSpeed 40ms

# Show version
Type "safari --version"
Enter
Sleep 1s

# Auth setup (simulated)
Type "safari auth setup"
Enter
Sleep 500ms
Type '{"groot_sessionid":"abc123","logged_in":"y","jwt":"eyJ...","csrf_access_token":"tok_..."}'
Enter
Sleep 1s

# Fetch a book
Type "safari fetch 9781491958698"
Enter
Sleep 500ms

# Simulated output (VHS will capture real output if safari is installed)
Sleep 3s

# Show completion
Sleep 2s
