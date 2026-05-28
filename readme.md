# WebRover

<div align="center">
  <!-- Backend -->
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/OpenAI-412991?style=for-the-badge&logo=openai&logoColor=white" />
  <img src="https://img.shields.io/badge/LangChain-121212?style=for-the-badge&logo=chainlink&logoColor=white" />
  <img src="https://img.shields.io/badge/LangGraph-FF6B6B?style=for-the-badge&logo=graph&logoColor=white" />
  <img src="https://img.shields.io/badge/Playwright-2EAD33?style=for-the-badge&logo=playwright&logoColor=white" />
  <img src="https://img.shields.io/badge/Pillow-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  
  <!-- Frontend -->
  <img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=next.js&logoColor=white" />
  <img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" />
  <img src="https://img.shields.io/badge/React-61DAFB?style=for-the-badge&logo=react&logoColor=black" />

  <h3>Your AI Co-pilot for Web Navigation 🚀</h3>

  <p align="center">
    <b>Autonomous Web Agent | Task Automation | Information Retrieval | Deep Research</b>
  </p>
</div>

# Overview
WebRover is an AI-powered web agent that combines autonomous browsing with advanced research capabilities. While maintaining its core ability to automate web tasks, version 2.0 introduces sophisticated research workflows including multi-source analysis, academic paper generation, and deep topic exploration. The system intelligently routes queries between task automation and research modes, providing a versatile tool for both quick actions and comprehensive research.

# Motivation
While traditional web automation tools excel at task execution, and search engines help with information retrieval, there's a growing need for tools that can handle both while specializing in deep research workflows. WebRover bridges this gap by offering task automation alongside intelligent research capabilities, with a particular focus on comprehensive information gathering, analysis, and synthesis. This dual-purpose approach aims to transform how we interact with web content, making both task execution and research more efficient and thorough.

## Demo Video - Deep Research Agent

https://github.com/user-attachments/assets/325c6c55-9384-4939-a912-3b1d13635799
> Watch as the WebRover Deep Research Agent explores a topic, gathers information, and generates an academic paper.

## Demo Video - Task Agent

https://github.com/user-attachments/assets/95ae9afb-3fdf-47f8-857e-f6a1a0d94df5
> Watch as the WebRover Task Agent navigates a website and performs a task.



## Key Features

### Agent Capabilities
- Three specialized agents for different use cases (Task, Research, Deep Research)
- Dynamic agent selection based on task complexity
- Real-time agent state visualization
- Streaming agent actions and thoughts

### Browser Integration
- Local browser instance for privacy and control
- Multi-tab management
- PDF document handling
- Secure browsing sessions

### User Interface
- Modern chat interface with real-time updates
- Interactive agent selection
- Action streaming with visual feedback
- Real-time page annotations and highlights

### Output Options
- Direct chat responses
- One-click Google Docs export
- PDF download functionality
- Copy to clipboard support

### Research Tools
- Vector store for information retention
- Multi-source verification
- Academic paper generation
- Reference management

### Technical Features
- State-of-the-art LLM integration (GPT-4o, o3-mini-high, Claude-3.5 sonnet)
- RAG pipeline for enhanced responses
- LangGraph for state management
- Playwright for reliable web automation

## Agent Types

### 1. Task Agent
A specialized automation agent for executing web-based tasks and workflows.
- Custom action planning for multi-step tasks
- Dynamic element interaction based on context
- Real-time task progress monitoring

### 2. Research Agent
An information gathering specialist with smart content processing.
- Intelligent source selection and validation
- Adaptive search refinement
- Single-pass comprehensive information gathering

### 3. Deep Research Agent (New! 🎉)
An advanced research agent that produces academic-quality content through systematic topic exploration.
- Automatic topic decomposition and structured research
- Independent subtopic exploration
- Academic paper generation with proper citations
- Cross-referenced bibliography compilation

### Agent Architecture Diagrams

#### Deep Research Agent Flow
![Deep Research Agent Architecture](assets/deep_research_agent.png)

*Deep Research Agent's workflow for comprehensive research and content generation*

### Research Agent Flow
![Research Agent Architecture](assets/research_agent.png)

*Research Agent's workflow for information gathering and synthesis*


#### Task Agent Flow
![Task Agent Architecture](assets/task_agent.png)

*Task Agent's workflow for automating web interactions*



## Architecture

The system is built on a modern tech stack with three distinct agent types, each powered by:

1. **State Management**
   - LangGraph for maintaining agent state
   - Handles complex navigation flows and decision making
   - Structured workflow management

2. **Browser Automation**
   - Playwright for reliable web interaction
   - Custom element detection and interaction system
   - Automated navigation and content extraction

3. **Content Processing**
   - RAG (Retrieval Augmented Generation) pipeline
   - Vector store integration for efficient information storage
   - PDF and webpage content extraction
   - Automatic content structuring and organization

4. **AI Decision Making**
   - Multiple LLM integration (GPT-4, Claude)
   - Context-aware navigation
   - Self-review mechanisms
   - Structured output generation

## Setup Instructions

### Backend Setup

1. Clone the repository
   ```bash
   git clone https://github.com/hrithikkoduri18/WebRover.git
   cd WebRover
   cd backend
   ```

2. Install Poetry (if not already installed)

   Mac/Linux:
   ```bash
   curl -sSL https://install.python-poetry.org | python3 -
   ```
   Windows:
   ```bash
   (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -
   ```

3. Set Python version for Poetry
   ```bash
   poetry env use python3.12
   ```

4. Activate the Poetry shell:
   For Unix/Linux/MacOS:
   ```bash
   poetry shell
   # or manually
   source $(poetry env info --path)/bin/activate
   ```
   For Windows:
   ```bash
   poetry shell
   # or manually
   & (poetry env info --path)\Scripts\activate
   ```

5. Install dependencies using Poetry:
   ```bash
   poetry install
   ```

6. Set up environment variables in `.env`:
   ```bash
   OPENAI_API_KEY="your_openai_api_key"
   LANGCHAIN_API_KEY="your_langchain_api_key"
   LANGCHAIN_TRACING_V2="true"
   LANGCHAIN_ENDPOINT="https://api.smith.langchain.com"
   LANGCHAIN_PROJECT="your_project_name"
   ANTHROPIC_API_KEY="your_anthropic_api_key"
   ```

7. Run the backend:

   Make sure you are in the backend folder

    ```bash
    uvicorn app.main:app --reload --port 8000 
    ```

   For Windows User:

    ```bash
    uvicorn app.main:app --port 8000
    ```

8. Access the API at `http://localhost:8000`

### Frontend Setup

1. Open a new terminal and make sure you are in the WebRover folder:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Run the frontend:
   ```bash
   npm run dev
   ```

4. Access the frontend at `http://localhost:3000`

For mac users: 

Try running http://localhost:3000 on Safari browser. 
If you face any with connecting to browser, open terminal and run:

```bash
pkill -9 "Chrome"
```
and try again.

If you still face issues, try changing the websocket port from 9222 to 9223 in the `webrover_browser.py` file in the `backend/Browser` folder.


## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

Made with ❤️ by [@hrithikkoduri](https://github.com/hrithikkoduri)

## ❓ FAQ

### What is WebRover?
WebRover is an AI-powered web agent that combines autonomous browsing with advanced research capabilities. It offers three specialized agents: Task Agent for web automation, Research Agent for information gathering, and Deep Research Agent for academic-quality content generation.

### Key Features
| Feature | Description |
|---------|-------------|
| **Three Agent Types** | Task, Research, Deep Research agents for different use cases |
| **Dynamic Selection** | Intelligent agent routing based on task complexity |
| **Real-time Visualization** | Streaming agent actions and thoughts |
| **Local Browser** | Privacy-focused local browser instance |
| **Multi-tab Management** | Handle multiple tabs simultaneously |
| **PDF Support** | Extract and process PDF documents |
| **Vector Store** | RAG pipeline for information retention |
| **Academic Papers** | Generate properly cited academic content |

### How to Install
```bash
git clone https://github.com/hrithikkoduri/WebRover.git
cd WebRover
# Follow Setup Instructions in readme.md
```

### Supported LLM Models
- GPT-4o
- o3-mini-high
- Claude-3.5 Sonnet

### Requirements
- Python (Backend)
- Node.js (Frontend)
- OpenAI/Claude API keys

### License
MIT License

### Help Resources
- [Issues](https://github.com/hrithikkoduri/WebRover/issues)
- [Demo Videos](https://github.com/hrithikkoduri/WebRover#demo-videos)
