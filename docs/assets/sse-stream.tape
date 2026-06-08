# Records docs/assets/sse-stream.gif: a real async workflow run streaming
# progress over SSE. Regenerate with:  vhs docs/assets/sse-stream.tape
# (requires the API + ARQ worker + Redis running locally; see README quickstart)
Output docs/assets/sse-stream.gif

Set Shell "bash"
Set FontSize 18
Set Width 1180
Set Height 380
Set Padding 22
Set TypingSpeed 45ms

Hide
Type "source .venv/bin/activate && clear"
Enter
Sleep 800ms
Show

Type "python scripts/stream_demo.py"
Sleep 600ms
Enter
Sleep 4s
