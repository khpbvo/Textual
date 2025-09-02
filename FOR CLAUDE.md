## There are some issue's with the program....Hope you can help!
## 1. Whenever a tool call is made bij an Agent, I notice the API calls are really slow. Check out terminator.log for the timings.
## 2. Some functionality does not work, like the DIFF screen, adjustable panels cannot be adjusted, menu options are somehow missing.
## 3. Whenever I open a Python file in the text editor I get the error: Error opening file: unhashable type: 'Theme'
## 4. Whenever I open a txt I get the error: tree-sitter but no built in or user-registered language called 'text'
## 5. The agent's cannot access the editor. They can create files on the system. They can search for files but they cannot see or interact with the code editor.
## 6. I cannot copy text from the terminal.
## 7. When I press ctrl plus space it should autocomple the code but instead I get this error:
╭─────────────────────────────────────────────────── Traceback (most recent call last) ────────────────────────────────────────────────────╮
│ /Users/kevinvanosch/Documents/TextualAgents/Textual/TerminatorV1_main.py:3594 in action_code_completion                                  │
│                                                                                                                                          │
│   3591 │   │   self.notify("Generating code completion...", severity="information")                                                      │
│   3592 │   │                                                                                                                             │
│   3593 │   │   # Request code completion from AI                                                                                         │
│ ❱ 3594 │   │   await self.call_ai_agent("Complete this code", code_context)                                                              │
│   3595 │                                                                                                                                 │
│   3596 │   def action_toggle_breakpoint(self) -> None:                                                                                   │
│   3597 │   │   """Toggle a breakpoint at the current line in the editor"""                                                               │
│                                                                                                                                          │
│ ╭──────────────────────────────────────────────────── locals ────────────────────────────────────────────────────╮                       │
│ │ code_context = 'print("Hello'                                                                                  │                       │
│ │       editor = TextArea(id='editor-primary')                                                                   │                       │
│ │         self = TerminatorApp(                                                                                  │                       │
│ │                │   title='Terminator - /Users/kevinvanosch/Documents/TextualAgents/Textual/requirements.tx'+1, │                       │
│ │                │   classes={'-dark-mode'},                                                                     │                       │
│ │                │   pseudo_classes={'dark', 'focus'}                                                            │                       │
│ │                )                                                                                               │                       │
│ ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
TypeError: object Worker can't be used in 'await' expression

## 8. Streaming text in the chat is no longer working. I suspect something is blocking the event loop I don't know what, but maybe it is the same thing that makes the API calls take long. When I ask a simple question in the chat the reply is reasonably fast. But when I ask the agent to perform some action that is related to code generation or something like that it reply's it cannot do it or the API call hangs.
## 9. When i activate pair programming mode I get this error:
(Imacvenv) kevinvanosch@Kevins-iMac Textual % python TerminatorV1_main.py
╭─────────────────────────────────────────────────── Traceback (most recent call last) ────────────────────────────────────────────────────╮
│ /Users/kevinvanosch/Documents/TextualAgents/Textual/Imacvenv/lib/python3.11/site-packages/textual/worker.py:368 in _run                  │
│                                                                                                                                          │
│   365 │   │   │   self.state = WorkerState.RUNNING                                                                                       │
│   366 │   │   │   app.log.worker(self)                                                                                                   │
│   367 │   │   │   try:                                                                                                                   │
│ ❱ 368 │   │   │   │   self._result = await self.run()                                                                                    │
│   369 │   │   │   except asyncio.CancelledError as error:                                                                                │
│   370 │   │   │   │   self.state = WorkerState.CANCELLED                                                                                 │
│   371 │   │   │   │   self._error = error                                                                                                │
│                                                                                                                                          │
│ ╭──────────────────────────────────────────────────────────── locals ─────────────────────────────────────────────────────────────╮      │
│ │           app = TerminatorApp(                                                                                                  │      │
│ │                 │   title='Terminator - /Users/kevinvanosch/Documents/TextualAgents/Textual/TerminatorV1_to'+6,                 │      │
│ │                 │   classes={'-dark-mode'},                                                                                     │      │
│ │                 │   pseudo_classes={'dark', 'focus'}                                                                            │      │
│ │                 )                                                                                                               │      │
│ │         error = TypeError("object Worker can't be used in 'await' expression")                                                  │      │
│ │          self = <Worker ERROR name='generate_pair_programming_suggestion' description='generate_pair_programming_suggestion()'> │      │
│ │ worker_failed = WorkerFailed('Worker raised exception: TypeError("object Worker can\'t be used in \'await\' expression")')      │      │
│ ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯      │
│                                                                                                                                          │
│ /Users/kevinvanosch/Documents/TextualAgents/Textual/Imacvenv/lib/python3.11/site-packages/textual/worker.py:352 in run                   │
│                                                                                                                                          │
│   349 │   │   Returns:                                                                                                                   │
│   350 │   │   │   Return value of the work.                                                                                              │
│   351 │   │   """                                                                                                                        │
│ ❱ 352 │   │   return await (                                                                                                             │
│   353 │   │   │   self._run_threaded() if self._thread_worker else self._run_async()                                                     │
│   354 │   │   )                                                                                                                          │
│   355                                                                                                                                    │
│                                                                                                                                          │
│ ╭──────────────────────────────────────────────────────── locals ────────────────────────────────────────────────────────╮               │
│ │ self = <Worker ERROR name='generate_pair_programming_suggestion' description='generate_pair_programming_suggestion()'> │               │
│ ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯               │
│                                                                                                                                          │
│ /Users/kevinvanosch/Documents/TextualAgents/Textual/Imacvenv/lib/python3.11/site-packages/textual/worker.py:337 in _run_async            │
│                                                                                                                                          │
│   334 │   │   │   or hasattr(self._work, "func")                                                                                         │
│   335 │   │   │   and inspect.iscoroutinefunction(self._work.func)                                                                       │
│   336 │   │   ):                                                                                                                         │
│ ❱ 337 │   │   │   return await self._work()                                                                                              │
│   338 │   │   elif inspect.isawaitable(self._work):                                                                                      │
│   339 │   │   │   return await self._work                                                                                                │
│   340 │   │   elif callable(self._work):                                                                                                 │
│                                                                                                                                          │
│ ╭──────────────────────────────────────────────────────── locals ────────────────────────────────────────────────────────╮               │
│ │ self = <Worker ERROR name='generate_pair_programming_suggestion' description='generate_pair_programming_suggestion()'> │               │
│ ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯               │
│                                                                                                                                          │
│ /Users/kevinvanosch/Documents/TextualAgents/Textual/TerminatorV1_main.py:3461 in generate_pair_programming_suggestion                    │
│                                                                                                                                          │
│   3458 │   │   concise. Don't rewrite everything, just suggest targeted improvements."""                                                 │
│   3459 │   │                                                                                                                             │
│   3460 │   │   # Call the AI with the pair programming prompt                                                                            │
│ ❱ 3461 │   │   await self.call_ai_agent(prompt, code_context)                                                                            │
│   3462 │   │                                                                                                                             │
│   3463 │   │   # Reset the timer to avoid constant suggestions                                                                           │
│   3464 │   │   self.last_edit_time = time.time()                                                                                         │
│                                                                                                                                          │
│ ╭──────────────────────────────────────────────────── locals ────────────────────────────────────────────────────╮                       │
│ │ code_context = '"""\nTerminatorV1 Tools - Utility tools for the Terminator IDE\nProvides file oper'+32166      │                       │
│ │       editor = TextArea(id='editor-primary')                                                                   │                       │
│ │       prompt = "As your AI pair programmer, I'm analyzing your code. \n        Please provide det"+210         │                       │
│ │         self = TerminatorApp(                                                                                  │                       │
│ │                │   title='Terminator - /Users/kevinvanosch/Documents/TextualAgents/Textual/TerminatorV1_to'+6, │                       │
│ │                │   classes={'-dark-mode'},                                                                     │                       │
│ │                │   pseudo_classes={'dark', 'focus'}                                                            │                       │
│ │                )                                                                                               │                       │
│ ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯                       │
╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
TypeError: object Worker can't be used in 'await' expression
