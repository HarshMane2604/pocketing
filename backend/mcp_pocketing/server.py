import httpx
from mcp.server.mcpserver import MCPServer
from datetime import datetime, timezone

mcp = MCPServer("Pocketing Lab")
POCKETING_API = "http://127.0.0.1:8010"


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
async def send_file(file_id: int) -> dict:
    """
    Prepare an uploaded Pocketing file for delivery.

    Use this when the user asks to send, share, or deliver
    an uploaded file.

    The file_id must come from Pocketing data.
    Never invent a file ID.

    This tool does not read or analyze the file contents.
    Use read_file_content when the user wants to understand
    what is inside the file.
    """

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{POCKETING_API}/api/files/{file_id}/send",
            timeout=30.0,
        )

        if response.status_code == 404:
            return {"error": f"File {file_id} not found"}

        response.raise_for_status()

        return response.json()

    
     




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
