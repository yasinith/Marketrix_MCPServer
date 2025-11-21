**Setup**

Clone the Repository:
git clone https://github.com/yasinith/Marketrix_MCPServer.git
cd Marketrix_MCPServer

Create Virtual Environment:
python -m venv .venv
.venv\Scripts\activate  # Windows; use 'source .venv/bin/activate' on macOS/Linux

Install Dependencies:
pip install -r requirements.txt

**Running the Server**

Start the Server
python mcp_server.py

**Integration with Claude Desktop**

Configure Claude:
Edit %APPDATA%\Claude\claude_desktop_config.json
{
  "mcpServers": {
    "web-interact": {
      "command": "npx",
      "args": [
        "mcp-remote", "http://127.0.0.1:8000/mcp/mcp"
      ],
      "cwd": "C:\\Users\\Acer\\AppData\\Local\\Temp",
      "env": {
        "NODE_ENV": "development",
        "DEBUG": "mcp-remote:*"
      }
    }
  }
}
