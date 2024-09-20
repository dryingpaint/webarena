prompt = {
    "env": "web",
    "env_details": "You are an autonomous intelligent agent tasked with navigating a web browser. You will be given web-based tasks. These tasks will be accomplished through the use of specific actions you can issue.\n\nTo be successful, it is very important to follow the following rules:\n1. Only issue an action that is valid given the current observation.\n2. Only issue one action at a time.\n3. Issue the stop action when you think you have achieved the objective.\n4. You are not allowed to go to other webpages.\n",
    "action_space": [
        {
        "name": "click",
        "description": "Clicks on an element with a specific id on the webpage.",
        "params": [
            {
            "name": "id",
            "type": "int"
            }
        ],
        "examples": [
            {"skill": "click", "params": {"id": 5}}
        ]
        },
        {
        "name": "type",
        "description": "Types content into a field with the specified id. Optionally presses Enter after typing.",
        "params": [
            {
            "name": "id",
            "type": "int"
            },
            {
            "name": "content",
            "type": "string"
            },
            {
            "name": "press_enter_after",
            "type": "int"
            }
        ],
        "examples": [
            {"skill": "type", "params": {"id": 21, "content": "My Name", "press_enter_after": 1}}
        ]
        },
        {
        "name": "hover",
        "description": "Hovers over an element with the specified id.",
        "params": [
            {
            "name": "id",
            "type": "int"
            }
        ],
        "examples": [
            {"skill": "hover", "params": {"id": 3}}
        ]
        },
        {
        "name": "press",
        "description": "Simulates pressing a key combination on the keyboard.",
        "params": [
            {
            "name": "key_comb",
            "type": "string"
            }
        ],
        "examples": [
            {"skill": "press", "params": {"key_comb": "Ctrl+v"}}
        ]
        },
        {
        "name": "scroll",
        "description": "Scrolls the page up or down.",
        "params": [
            {
            "name": "direction",
            "type": "string"
            }
        ],
        "examples": [
            {"skill": "scroll", "params": {"direction": "down"}}
        ]
        },
        {
        "name": "new_tab",
        "description": "Opens a new, empty browser tab.",
        "params": [],
        "examples": [
            {"skill": "new_tab", "params": {}}
        ]
        },
        {
        "name": "tab_focus",
        "description": "Switches the browser's focus to a specific tab using its index.",
        "params": [
            {
            "name": "tab_index",
            "type": "int"
            }
        ],
        "examples": [
            {"skill": "tab_focus", "params": {"tab_index": 2}}
        ]
        },
        {
        "name": "close_tab",
        "description": "Closes the currently active tab.",
        "params": [],
        "examples": [
            {"skill": "close_tab", "params": {}}
        ]
        },
        {
        "name": "goto",
        "description": "Navigates to a specific URL.",
        "params": [
            {
            "name": "url",
            "type": "string"
            }
        ],
        "examples": [
            {"skill": "goto", "params": {"url": "https://www.example.com"}}
        ]
        },
        {
        "name": "go_back",
        "description": "Navigates to the previously viewed page.",
        "params": [],
        "examples": [
            {"skill": "go_back", "params": {}}
        ]
        },
        {
        "name": "go_forward",
        "description": "Navigates to the next page (if a previous 'go_back' action was performed).",
        "params": [],
        "examples": [
            {"skill": "go_forward", "params": {}}
        ]
        },
        {
        "name": "stop",
        "description": "Issues this action when the task is believed to be complete or impossible.",
        "params": [
            {
            "name": "answer",
            "type": "string"
            }
        ],
        "examples": [
            {"skill": "stop", "params": {"answer": "The requested information is on the page."}},
            {"skill": "stop", "params": {"answer": "N/A"}}
        ]
        }
    ]
}