import httpx, os, shutil, tempfile
from mcp.server.mcpserver import MCPServer
from datetime import datetime, timezone
import asyncio, os
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv

load_dotenv()
GITHUB_PAT = os.getenv("GITHUB_PAT")

mcp = MCPServer("Pocketing Lab")
POCKETING_API = "http://127.0.0.1:8010"
SANDBOX_DIR = Path("/home/harsh/pocketing/pocketing/sandbox")


class DDGHTMLParser(HTMLParser):
    """Parse DuckDuckGo HTML search results page"""
    def __init__(self):
        super().__init__()
        self.results = []
        self.current_result = None
        self.in_result = False
        self.in_title = False
        self.in_snippet = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        # DuckDuckGo HTML results wrap each result in a div with result__body class
        if tag == "div" and "result__body" in attrs_dict.get("class", ""):
            self.current_result = {"title":  "", "link": "", "snippet": ""}
            self.in_result = True
        elif self.in_result:
            if tag == "a" and "result__url" in attrs_dict.get("class", ""):
                self.current_result["link"] = attrs_dict.get("href", "")
                self.in_title = True
            elif tag == "a" and "result__snippet" in attrs_dict.get("class", ""):
                self.in_snippet = True
                
    def handle_endtag(self, tag):
        if tag == "div" and self.in_result:
            if self.current_result:
                self.results.append(self.current_result)
            self.current_result = None
            self.in_result = False
        elif tag == "a" and self.in_title:
            self.in_title = False
        elif tag == "a" and self.in_snippet:
            self.in_snippet = False
    
    def handle_data(self, data):
        if self.in_title and self.current_result:
            self.current_result["title"] += data
        elif self.in_snippet and self.current_result:
            self.current_result["snippet"] += data

class HTMLToTextParser(HTMLParser):
    """Converts webpage HTML to clean structured text for LLM reading."""
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.current_tag = None
        self.skip_tags = {"script", "style", "head", "nav", "header", "footer", "noscript"}
        self.in_skip_block = 0
    
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag.lower()
        if self.current_tag in self.skip_tags:
            self.in_skip_block += 1
    
    def handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower in self.skip_tags:
            self.in_skip_block = max(0, self.in_skip_block - 1)
        self.current_tag = None     

    def handle_data(self, data):
        if self.in_skip_block == 0:
            cleaned = data.strip()
            if cleaned:
                # Add linebreaks around blocks to maintain layout structures
                if self.current_tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "li", "tr"}:
                    self.text_parts.append("\n" + cleaned + "\n")
                else:
                    self.text_parts.append(cleaned + " ")

    def get_text(self):
        # Join text and collapse consecutive newlines
        full_text = "".join(self.text_parts)
        lines = [line.strip() for line in full_text.splitlines()]
        cleaned_lines = []
        for line in lines:
            if line:
                cleaned_lines.append(line)
            elif not cleaned_lines or cleaned_lines[-1] != "":
                cleaned_lines.append("")

        return "\n".join(cleaned_lines).strip()

def clean_ddg_url(url: str) -> str:
    """Extracts the actual destination URL from DuckDuckGo redirect link."""
    if url.startswith("//"):
        url = "https:" + url
    if "/l/?uddg=" in url:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return url



now = datetime.now(timezone.utc).isoformat()



@mcp.tool()
async def list_notes(
    is_done: bool | None=None,
    is_pinned: bool | None=None 
) -> list[dict]:
    """
    List saved Pocketing notes.

    Use this when the user asks to see or list their notes,
    tasks, completed items, unfinished items, or pinned items.

    Optional filters:
    - is_done=True: completed notes
    - is_done=False: unfinished notes
    - is_pinned=True: pinned notes
    - is_pinned=False: unpinned notes
    """

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{POCKETING_API}/api/notes",
            timeout=10.0,
        )
        response.raise_for_status()
        notes = response.json()
    
    if is_done is not None:
        notes = [
            note
            for note in notes
            if note["is_done"] == is_done
        ]
    
    if is_pinned is not None:
        notes = [
            note
            for note in notes
            if note["is_pinned"] == is_pinned
        ]
    
    return [
        {
            "id": note["id"],
            "content": note["content"],
            "source": note["source"],
            "created_at": note["created_at"],
            "is_pinned": note["is_pinned"],
            "is_done": note["is_done"],
            "priority": note["priority"],
        }
        for note in notes
    ]




@mcp.tool()
async def search_resources(query: str) -> list[dict]:
    """
    Search saved Pocketing notes.

    Use this for finding text notes, reminders,
    tasks, ideas, or saved information.

    DO NOT use this tool when the user is looking
    for an actual uploaded file, document, image,
    PDF, video, audio, attachment, or media file.

    Examples:
    - "Find my Redis note"
    - "Show my backend notes"
    - "Find the note about MCP"
    - "What did I save about Python?"
    """

    query = query.lower()
    results = []

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{POCKETING_API}/api/notes",
            params={"search": query},
            timeout=10.0
        )

        response.raise_for_status()
        notes = response.json()
    return [
        {
            "id": note["id"],
            "content": note["content"],
            "source" : note["source"],
            "created_at": note["created_at"],
            "is_pinned": note["is_pinned"],
            "is_done": note["is_done"],
            "priority": note["priority"]
        }
        for note in notes
    ] 


@mcp.tool()
async def get_resource(resource_id: int) -> dict:
    """
    Retrieve the complete details of a Pocketing resource.

    Use this tool when a specific resource ID is known
    and the user requests its full details.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{POCKETING_API}/api/notes",
            timeout=10.0,
        )

        response.raise_for_status()
        notes = response.json()

    for note in notes:
        if note["id"] == resource_id:
            return note    

    return {"error": f"Resource {resource_id} not found"}


@mcp.tool()
async def create_note(content:str):
    """
    Create a note in Pocketing.

    Use this when user asks to remember, save,
    add, or create a new note.

    """
    if not content.strip():
        return {"error": "Note content cannot be empty"}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{POCKETING_API}/api/notes",
            data={"content": content.strip()},
            timeout=10.0,
        ) 

        response.raise_for_status()

        return response.json()


@mcp.tool()
async def update_note(
    note_id: int, 
    content: str | None = None,
    is_pinned: str | None = None,
    is_done: bool | None = None, 
    priority: int | None = None
) -> dict:
    """
    Search saved Pocketing notes.

    Use this tool whenever the user wants to find,
    search, locate, discover, or modify something
    they previously saved.

    Search using a concise keyword or phrase extracted
    from the user's request.

    IMPORTANT:
    If the search returns no results, do not immediately
    conclude that the resource does not exist.

    Try another broader keyword from the user's request.
    For example, if "Redis learning goal" returns no
    results, try "Redis".

    Return lightweight results containing note IDs.

    When modifying a note, use the returned ID with
    update_note.
    """

    payload = {}

    if content is not None:
        payload["content"] = content.strip()
    if is_pinned is not None:
        payload["is_pinned"] = is_pinned
    if is_done is not None:
        payload["is_done"] = is_done
    if priority is not None:
        payload["priority"] = priority

    if not payload:
        return {"error": "No fields were provided"}

    async with httpx.AsyncClient() as client:
        response = await client.patch(
            f"{POCKETING_API}/api/notes/{note_id}",
            json=payload,
            timeout=10.0,
        ) 
    
        if response.status_code == 404:
            return {"error": f"Note {note_id} not found"}
        response.raise_for_status()

        return response.json()


@mcp.tool()
async def search_files(query: str, file_type:str | None = None,) -> list[dict]:
    """
    Search uploaded files and attachments in Pocketing.

    Use this when the user wants an actual file,
    document, PDF, image, video, audio, attachment,
    or uploaded media.

    query:
        Filename or related search term.

    file_type:
        Optional category such as image, video,
        audio, or document
    
    Examples:
    - "Find my resume"
    - "Find my resume PDF"
    - "Show me the Python PDF I uploaded"
    - "Find the screenshot I uploaded"
    - "Find my project documentation"
    - "Locate my CV"
    - "Find the file attached to my interview note"
    """

    params = {
        "search": query,
    }

    if file_type:
        params["type"] = file_type
    
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{POCKETING_API}/api/files",
            params=params,
            timeout=10.0,
        ) 

        response.raise_for_status()

    
        return response.json()

@mcp.tool()
async def get_file_info(file_id: int) -> dict:
    """
    Get metadata and information about an uploaded Pocketing file.

    Use this when user wants details or metadata
    about a file that has already been identified.

    This tool does NOT download file.

    The file_id must come from pocketing data.
    Never invet a file ID. 
    """

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{POCKETING_API}/api/files/{file_id}/info",
            timeout=10.0,
        )

        if response.status_code == 404:
            return {"error": f"File {file_id} not found"}
        
        response.raise_for_status()

        return response.json()

@mcp.tool()
async def read_file_info(file_id: int) -> dict:
    """
    Read and extract text from stored Pocketing file.

    Use this when the user asks what a file contains,
    wants to read, analyze, summaries, or understand a document.
    
    The file_id must come from Pocketing data.
    Do not invent file IDs
    """

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{POCKETING_API}/api/files/{file_id}/content",
            timeout = 30.0
        )

        response.raise_for_status()

        return response.json()


@mcp.tool()
async def send_file(file_id: int | None = None, filename: str | None = None) -> dict:
    """
    Send/deliver a file to the user's Telegram.

    Use this when the user asks to send, share, or download a file.
    You must provide EXACTLY ONE of the parameters:
    - If the file is a stored Pocketing resource, pass 'file_id' (must come from Pocketing data).
    - If the file is in the local sandbox workspace (e.g. index.html or a zip file), pass 'filename'.
    """
    if file_id is not None and filename is not None:
        return {"error": "Provide either 'file_id' or 'filename', not both."}
    if file_id is None and filename is None:
        return {"error": "You must provide either 'file_id' or 'filename'."}

    async with httpx.AsyncClient() as client:
        if file_id is not None:
            response = await client.post(
                f"{POCKETING_API}/api/files/{file_id}/send",
                timeout=30.0,
            )
            if response.status_code == 404:
                return {"error": f"File {file_id} not found"}
            response.raise_for_status()
            return response.json()
        else:
            response = await client.post(
                f"{POCKETING_API}/api/files/send-local",
                json={"filename": filename},
                timeout=60.0
            )
            if response.status_code == 404:
                return {"error": f"File '{filename}' not found in sandbox"}
            elif response.status_code == 403:
                return {"error": "Access denied: Cannot send files outside the sandbox."}
            response.raise_for_status()
            return response.json()


@mcp.tool()
async def write_file(filename: str, content: str) -> dict:
    """
    Create or write a file with text content in the local sandbox.

    Use this when the user wants to write code, save a script, edit text,
    or write files locally in the project workspace (e.g., hello_world.py).

    Parameters:
    - filename: The name of the file to write (e.g. 'hello_world.py')
    - content: The content of the file
    """
    try:
        SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        file_path = SANDBOX_DIR / filename
        
        # Security: Prevent path traversal outside the sandbox folder
        if not file_path.resolve().is_relative_to(SANDBOX_DIR.resolve()):
            return {"error": "Access denied: Cannot write files outside the sandbox directory."}

        # Auto-create parent folders if writing to a subdirectory
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "message": f"Successfully wrote to {filename}",
            "file_path": str(file_path)
        }
    except Exception as e:
        return {"error": f"Failed to write file: {str(e)}"}


@mcp.tool()
async def run_local_command(command: str) -> dict:
    """
    Run a local terminal/bash command in the sandbox directory.

    Use this to execute Python scripts, compile code, run tests, or run command-line
    utilities relative to the sandbox directory (e.g., 'python3 hello_world.py').

    Parameters:
    - command: The shell command to execute (e.g. 'python3 hello_world.py')
    """
    try:
        SANDBOX_DIR.mkdir(parents=True, exist_ok=True)
        
        # Spawn execution in subprocess using asyncio to keep things non-blocking
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(SANDBOX_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        try:
            # 30 seconds execution timeout
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")
            
            return {
                "exit_code": proc.returncode,
                "stdout": stdout,
                "stderr": stderr
            }
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {"error": "Command execution timed out after 30 seconds."}
            
    except Exception as e:
        return {"error": f"Failed to execute command: {str(e)}"}

@mcp.tool()
async def create_local_directory(directory_name: str) -> dict:
    """
    Create a new folder/directory inside the local sandbox workspace.

    Use this when you need to establish folder structures, e.g., 'css', 'js',
    or other subdirectories.

    Parameters:
    - directory_name: The name/path of the directory to create (e.g. 'css' or 'js/modules')
    """
    try:
        dir_path = SANDBOX_DIR / directory_name
        
        # Security: Prevent path traversal
        if not dir_path.resolve().is_relative_to(SANDBOX_DIR.resolve()):
            return {"error": "Access denied: Cannot create directories outside the sandbox."}
            
        dir_path.mkdir(parents=True, exist_ok=True)
        return {
            "success": True,
            "message": f"Successfully created directory '{directory_name}'",
            "directory_path": str(dir_path)
        }
    except Exception as e:
        return {"error": f"Failed to create directory: {str(e)}"}


@mcp.tool()
async def list_local_files() -> dict:
    """
    List all files and directories currently present in the local sandbox workspace.

    Use this to check if a file/folder already exists before creating it,
    or to see what files are available to run or read.
    """
    try:
        if not SANDBOX_DIR.exists():
            return {"files": []}

        files = []
        for path in SANDBOX_DIR.iterdir():
            is_dir = path.is_dir()
            files.append({
                "filename": path.name,
                "type": "directory" if is_dir else "file",
                "size_bytes": 0 if is_dir else path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
            })
        return {"files": files}
    except Exception as e:
        return {"error": f"Failed to list files: {str(e)}"}

@mcp.tool()
async def read_local_file(filename: str) -> dict:
    """
    Read the complete content of a file in the local sandbox workspace.

    Use this when you want to view, check, or edit the existing contents
    of a script/file in the sandbox directory.

    Parameters:
    - filename: The name of the file to read (e.g. 'hello_world.py')
    """
    try:
        file_path = SANDBOX_DIR / filename
        if not file_path.resolve().is_relative_to(SANDBOX_DIR.resolve()):
            return {"error": "Access denied: Cannot read files outside the sandbox directory."}

        if not file_path.exists():
            return {"error": f"File '{filename}' does not exist in the sandbox."}

        content = file_path.read_text(encoding="utf-8")
        return {
            "filename": filename,
            "content": content
        }
    except Exception as e:
        return {"error": f"Failed to read file: {str(e)}"}

@mcp.tool()
async def patch_local_file(filename:str, target_text: str, replacement_text: str) -> dict:
    """
    Search and replace a specific block of text inside a file in sandbox workspace.

    Use this to edit specific lines of code in a file (e.g. style.css or index.html)
    without rewriting the entire file. The 'target_text' Must match the existing
    text exactly, including spacing, indentation, and newlines, and must be unique in the file.

    Parameters:
    - filename: The name of the file to modify (e.g. 'style.css')
    - target_text: The exact block to text to search for (must be unique in the file)
    - replacement_text: The new block of text to replace the target_text with 
    """

    try:
        file_path = SANDBOX_DIR/ filename

        # Security: Prevent path traversal outside the sandox folder
        if not file_path.resolve().is_relative_to(SANDBOX_DIR.resolve()):
            return {"error": "Access denied: Cannot edit files outside teh sandbox directory."}
        if not file_path.is_file():
            return {"error": f"File '{filename}' does not exist in sandbox."}
        content = file_path.read_text(encoding="utf-8")
        count = content.count(target_text)
        if count == 0:
            return {"error": "The target_text was not found in the file. Make sure it matches spacing, indentation, and newlines exactly."}
        elif count > 1:
            return {"error": f"The target_text is not unique (found {count} occurrences). Please include more lines of surrounding code as context."}

        new_content = content.replace(target_text, replacement_text)
        file_path.write_text(new_content, encoding="utf-8")

        return {
            "success": True,
            "message": f"Successfully patched {filename}."
        }
    except Exception as e:
        return {"error": f"Failed to patch file: {str(e)}"}

@mcp.tool()
async def grep_local_files(query: str) -> dict:
    """
    Search recursively for a query string/pattern inside all files in the sandbox workspace.

    Use this when you need to find where a specific function, css slate, variable, class, decorator, api
    or HTML tag is defined or used across all files in the project

    Parameters:
    - query: The text search term to locate (case-sensitive)
    """
    try:
        if not SANDBOX_DIR.exists():
            return {"matches": []}
        
        matches = []

        max_matches = 50 # Limit to prevent bloating Qwen's context window

        # Walk recursively through all directories in the sandbox
        for root, dirs, files in os.walk(str(SANDBOX_DIR)):
            for file in files:
                file_path = Path(root)/file

                # Security: Prevent traversing outside the sandbox
                if not file_path.resolve().is_relative_to(SANDBOX_DIR.resolve()):
                    continue
                try:
                     # Read as text, ignoring encoding errors for binary/non-UTF8 files
                     content = file_path.read_text(encoding="utf-8", errors="ignore")

                     if query in content:
                        lines = content.splitlines()
                        for line_idx, line in enumerate(lines):
                            if query in line:
                                relative_path = file_path.relative_to(SANDBOX_DIR)
                                matches.append({
                                    "filename": str(relative_path),
                                    "line_number": line_idx + 1,
                                    "line_content": line.strip()
                                })
                                if len(matches) >= max_matches:
                                    return {
                                        "matches": matches,
                                        "warning": f"Reached the limit of {max_matches} matches."
                                    }
                except Exception:
                    continue
        return {"matches": matches}
    except Exception as e:
        return {"error": f"Failed to grep files: {str(e)}"}

@mcp.tool()
async def zip_sandbox_workspace(zip_name: str) -> dict:
    """
    Compress/zip the entire local sandbox workspace into single .zip file.

    Use this when you have created or updated multiple files (e.g. HTML, CSS, JS, folders)
    and want to bundle them together so the user can easily download the whole project.

    Parameters:
    - zip_name: The filename for the output zip (e.g. 'landing_page.zip')
    """

    try:
        # security: Prevent path traversal
        zip_path = SANDBOX_DIR / zip_name
        if not zip_path.resolve().is_relative_to(SANDBOX_DIR.resolve()):
            return {"error": "Access Denied - Cannot write zip file outside the sandbox."}
        
        if not zip_name.lower().endswith(".zip"):
            zip_name += ".zip"
        
        final_path = SANDBOX_DIR / zip_name

        # Compress to a temp directory first to avoid zipping the output file itself

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_base = os.path.join(tmpdir, "workspace")

            #create the archive
            archive_path = shutil.make_archive(
                base_name = tmp_base,
                format="zip",
                root_dir=str(SANDBOX_DIR),
                base_dir="."
            )

            # Move the completed zip file to the sandbox directory
            if final_path.exists():
                os.remove(final_path)
            shutil.move(archive_path, str(final_path))
        return {
            "success": True,
            "message": f"Successfully zipped workspace into {zip_name}.",
            "filename": zip_name,
            "size_bytes": final_path.stat().st_size
        }
    except Exception as e:
        return {"error": f"Failed to zip workspace: {str(e)}"}

@mcp.tool()
async def search_web(query: str) -> dict:
    """
    Search the web for information or documentation using DuckDuckGo.

    Use this when you need to look up documentation for APIs, libraries,
    code examples, or solutions to errors you encounter.

    Parameters:
    - query: The search term to query (e.g. 'fastapi websocket documentation')
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=headers,
                timeout=15.0
            )
            response.raise_for_status()
            
            parser = DDGHTMLParser()
            parser.feed(response.text)
            
            formatted_results = []
            for res in parser.results[:8]:
                link = clean_ddg_url(res["link"])
                formatted_results.append({
                    "title": res["title"].strip(),
                    "link": link,
                    "snippet": res["snippet"].strip()
                })
                
            return {"results": formatted_results}
    except Exception as e:
        return {"error": f"Failed to search web: {str(e)}"}

@mcp.tool()
async def fetch_url(url: str) -> dict:
    """
    Fetch and read the main text content of a webpage or documentation page.

    Use this when search_web returns a link to a documentation page or website,
    and you need to read its content to understand how to use an API or fix a bug.

    Parameters:
    - url: The full HTTP/HTTPS URL of the page to read (e.g. 'https://docs.python.org/3/')
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=20.0)
            response.raise_for_status()
            
            parser = HTMLToTextParser()
            parser.feed(response.text)
            text_content = parser.get_text()
            
            # Truncate content to max 15,000 characters to prevent context window blowup
            truncated = len(text_content) > 15000
            content = text_content[:15000]
            if truncated:
                content += "\n\n[Content truncated due to length limit...]"
                
            return {
                "url": url,
                "content": content,
                "character_count": len(text_content)
            }
    except Exception as e:
        return {"error": f"Failed to fetch URL: {str(e)}"}

#-----GITHUB_MCP------

#----- Search Repo -------
@mcp.tool()
async def search_github(
    query: str,
    scope: str = "all"
)-> dict:
    """
    Search GitHub repositories.

    Use ONLY when the user is asking about GitHub repositories,
    projects, or code hosted on GitHub.

    Parameters:
    - query: The search term (e.g. "Pocketing", "resume analyzer")
    - scope: Set to "mine" to search ONLY the authenticated user's repositories (e.g. for "my repository", "my project", "my code"). Set to "all" to search all public repositories on GitHub. Default is "all".

    Do NOT use this for:
    - Pocketing notes
    - Pocketing files
    - local sandbox files
    - general web searches

    Examples:
    - "Find my Pocketing repository" -> query="Pocketing", scope="mine"
    - "Search GitHub for MCP projects" -> query="MCP", scope="all"
    - "Find my resume analyzer repo" -> query="resume analyzer", scope="mine"
    - Do not call another tool after search_github unless the user explicitly asks for more details.
    """
    if not query.strip():
        return {"error": "GitHub search query cannot be empty"}
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {GITHUB_PAT}",
        "X-Github-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient() as client:
        actual_query = query.strip()
        
        if scope == "mine":
            user_resp = await client.get("https://api.github.com/user", headers=headers, timeout=10.0)
            if user_resp.status_code == 200:
                username = user_resp.json().get("login")
                if username:
                    actual_query += f" user:{username}"

        params = {
            "q": actual_query,
            "per_page": 10
        }
        response = await client.get(
            "https://api.github.com/search/repositories",
            headers=headers,
            params=params,
            timeout=15.0,
        )

        if response.status_code == 401:
            return {"error": "Github authentication failed"}

        if response.status_code == 403:
            return {"error": "Github API rate limit or permission error"}

        response.raise_for_status()

        data = response.json()

        results = [
            {
                "name": repo["name"],
                "full_name": repo["full_name"],
                "description": repo["description"],
                "url": repo["html_url"],
                "private": repo["private"],
                "default_branch": repo["default_branch"],
                "stars": repo["stargazers_count"],
                "language": repo["language"],
            }
            for repo in data.get("items", [])
        ]
        
        response_data = {"results": results}
        if not results:
            response_data["note"] = (
                "No repositories found. If you are looking for a private repository or a repository owned by an "
                "organization, make sure your GITHUB_PAT is configured to grant access to it (fine-grained tokens "
                "require explicit authorization for other organizations)."
            )
        return response_data

#---- list_github_prs ----

@mcp.tool()
async def list_github_prs(repository: str, state:str = "open") -> dict:
    """
    List pull requests for a GitHub repository.

    Use this when the user asks whether anyone has raised a PR,
    wants to see open pull requests, or wants to inspect team PRs.

    repository must be in owner/name format.

    state can be:
    - open
    - closed
    - all

    Examples:
    - "Are there any PRs on my Pocketing repo?"
    - "Show me the open PRs in Pocketing."
    - "Has anyone raised a PR?"
    """

    if not repository:
        return {"error": "Repository name not mentioned"}
    
    async with httpx.AsyncClient() as client:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        if GITHUB_PAT:
            headers["Authorization"] = f"Bearer {GITHUB_PAT}"

        # If the repository is just the name (e.g. "Pocketing"), resolve the owner automatically
        if "/" not in repository:
            user_resp = await client.get("https://api.github.com/user", headers=headers, timeout=10.0)
            if user_resp.status_code == 200:
                username = user_resp.json().get("login")
                if username:
                    repository = f"{username}/{repository}"

        params = {
            "state": state,
            "per_page": 50,
            "page": 1,
        }

        response = await client.get(
            f"https://api.github.com/repos/{repository}/pulls",
            headers=headers,
            params=params,
            timeout=15.0
        )

        if response.status_code == 401:
            return {"error": "Github authentication failed"}

        if response.status_code == 403:
            return {"error": "Github API rate limit or permission error"}

        if response.status_code == 404:
            return {
                "error": (
                    f"Repository '{repository}' not found. Please verify the owner/name format. "
                    "If the repository exists and is private/organization-owned, make sure your GITHUB_PAT "
                    "token is authorized to access it (fine-grained tokens do not have access to other "
                    "organizations by default)."
                )
            }

        response.raise_for_status()

        data = response.json()
        pull_requests = [] 
        for pr in data:
            pull_requests.append({
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["user"]["login"],
                "state": pr['state'],
                "head_branch": pr["head"]["ref"],
                "base_branch": pr["base"]["ref"],
                "url": pr["html_url"],
                "created_at": pr["created_at"],
                "updated_at": pr["updated_at"],
            })
        
        return {
            "results": [
                {
                "repository": repository,
                "state": state,
                "pull_requests": pull_requests
                }
            ]
        }





if __name__ == "__main__":
    import sys
    if "--http" in sys.argv:
        # Run as a persistent SSE HTTP server (for systemd / daemon mode)
        # Default: http://127.0.0.1:8011/sse
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--http", action="store_true")
        parser.add_argument("--host", default="127.0.0.1")
        parser.add_argument("--port", type=int, default=8011)
        args = parser.parse_args()
        import uvicorn
        uvicorn.run(mcp.sse_app(), host=args.host, port=args.port)
    else:
        # Default stdio mode (used by ai_client.py / client.py)
        mcp.run()
