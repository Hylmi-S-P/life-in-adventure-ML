## 2026-07-14T11:25:08Z

A Session Event Logger and User Feedback System for the Life in Adventure AI Quest Assistant to record decision logs, screenshots, and allow users to submit success/failure evaluations with optional failure reasons in a dedicated feedback window.

Working directory: D:\LifeInAdventure-Tools\LifeInAdventure-Tools
Integrity mode: development

## Requirements

### R1. Separate Feedback & Session History Window
- Implement a dedicated "Session Logs & Feedback" window using CustomTkinter that is opened when the auto-play loop stops working, is paused, or disabled.
- The window should display a scrollable chronological list of recent events encountered during the active session.
- For each log entry, display the timestamp, event key, OCR text snippet, recommended choice, and the associated screenshot.

### R2. Success / Failure Evaluation & Comments
- Provide `✅ Success` and `❌ Failure` buttons for each event in the list.
- If marked `❌ Failure`, display an entry field for the user to optionally write a failure reason/comment.
- If marked `✅ Success`, immediately save the record and visually mark it as reviewed without prompting for a reason.

### R3. Session Log Capturing
- When the bot is running, it must automatically capture and save the screen image to `data/session_history/screenshots/<timestamp>_<event_key>.png` whenever a RAG search is performed.
- Log details (timestamp, event_key, ocr_text, choice_recommended, choice_index, screenshot_path) must be temporarily buffered in memory during the active session.

### R4. Persistent Database Storage
- When feedback is submitted, save the review record (event metadata, feedback status, optional comments, and screenshot path) into a persistent database (either a SQLite database `data/session_history/feedback.sqlite` or a JSON lines file `data/session_history/feedback.jsonl`).

## Acceptance Criteria

### UI Acceptance
- [ ] Toggling auto-play off or pausing launches the new "Session Logs & Feedback" window.
- [ ] The feedback window renders event details, screenshot images, and success/failure button options correctly.
- [ ] Users can enter optional text comments for failed options.

### Code Integrity & Tests
- [ ] Create a test file `tests/test_session_logger.py` containing automated tests that assert:
  - Event capture records log details and saves screenshot files.
  - Submitting success/failure feedback writes persistent records into the database file.
- [ ] All 10 tests in the project test suite pass successfully (`python -m unittest discover tests`).
