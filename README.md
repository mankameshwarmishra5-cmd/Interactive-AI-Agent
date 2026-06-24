# Interactive AI Agent

An intelligent AI Assistant built with **FastAPI**, **Google Gemini 2.5 Flash**, **SQLite Memory**, and a modern web dashboard.

## Features

### AI Chat
- Gemini 2.5 Flash integration
- Session-based conversations
- Intelligent fallback mode when API is unavailable
- Markdown-formatted responses

### Memory System
- Persistent chat history using SQLite
- Session management
- Automatic history summarization
- Context retention across messages

### Tool System
Built-in tools:

- Calculator
- Current Time
- System Status
- Web Search

The AI can automatically invoke tools when required.

### Dashboard
- Modern web interface
- Real-time chat
- Session tracking
- Streaming responses
- Agent status monitoring

### Performance Features
- Retry mechanism
- Error classification
- Graceful fallback handling
- Request timeout protection

---

# Tech Stack

| Component | Technology |
|------------|------------|
| Backend | FastAPI |
| AI Model | Gemini 2.5 Flash |
| Database | SQLite |
| Frontend | HTML, CSS, JavaScript |
| Server | Uvicorn |
| Memory | Custom Conversation Memory System |

---

# Project Structure

```text
Interactive-AI-Agent/
│
├── agent.py
├── main.py
├── database.py
├── cli.py
├── requirements.txt
│
├── tools/
│   ├── calculator.py
│   ├── current_time.py
│   ├── system_status.py
│   └── web_search.py
│
├── memory/
│
├── static/
│   ├── index.html
│   ├── style.css
│   └── script.js
│
└── logs/
```

---

# Installation

## 1. Clone Repository

```bash
git clone https://github.com/mankameshwarmishra5-cmd/Interactive-AI-Agent.git

cd Interactive-AI-Agent
```

---

## 2. Create Virtual Environment

### Windows

```powershell
python -m venv venv

.\venv\Scripts\Activate.ps1
```

### Linux / Mac

```bash
python3 -m venv venv

source venv/bin/activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## 4. Configure Environment Variables

Create a file named:

```text
.env
```

Add:

```env
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
```

Get a Gemini API key from:

https://aistudio.google.com/

---

## 5. Run Application

```bash
python main.py
```

Server:

```text
http://127.0.0.1:8000
```

---

# API Endpoints

## Chat

```http
POST /api/chat
```

Request:

```json
{
  "message": "Hello",
  "session_id": "default"
}
```

---

## Stream Chat

```http
GET /api/chat/stream
```

---

## Agent Status

```http
GET /api/status
```

---

## Metrics

```http
GET /api/metrics
```

---

# Tool Usage

The AI can automatically call tools using:

```text
TOOL:calculator:2+2
```

Example:

```text
TOOL:current_time
```

```text
TOOL:system_status
```

```text
TOOL:web_search:latest AI news
```

---

# Memory System

Conversation history is stored in SQLite.

Features:

- Persistent sessions
- History loading
- History clearing
- Automatic summarization
- Memory compression

---

# Error Handling

The system automatically detects:

- Invalid API Keys
- Gemini Quota Limits
- Network Errors
- SDK Issues
- Timeouts

Fallback responses are provided when Gemini becomes unavailable.

---

# Development

Run with hot reload:

```bash
uvicorn main:app --reload
```

---

# Future Improvements

- Multi-Agent Architecture
- RAG Support
- Vector Database Memory
- Voice Input
- Voice Output
- File Upload Support
- PDF Analysis
- Resume Analysis
- Web Browsing Agent
- Autonomous Task Execution

---


# Author

**Mankameshwar Mishra**

GitHub:

https://github.com/mankameshwarmishra5-cmd

---

# License

MIT License

Copyright (c) 2026 Mankameshwar Mishra

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files to deal in the Software without restriction.
