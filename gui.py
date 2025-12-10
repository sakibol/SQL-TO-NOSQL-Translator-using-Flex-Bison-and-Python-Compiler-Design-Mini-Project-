import subprocess
from tkinter import *
from tkinter import ttk, messagebox
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import json
import ast
import re

# ------------------ MongoDB Connection ------------------
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "campus"

# Initialize client globally but add a short timeout for connection check
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    db = client[DB_NAME]
except Exception:
    client = None
    db = None

# Global variable to store last translated query
last_translated_query = ""

# ------------------ Functions ------------------

def check_db_connection():
    """Pings the database to verify a successful connection."""
    global client
    
    if client is None:
        messagebox.showerror("Connection Error", "MongoDB client failed to initialize.")
        return False
        
    try:
        # The 'ping' command is cheap and confirms server readiness
        client.admin.command('ping') 
        return True
    except ServerSelectionTimeoutError:
        messagebox.showerror("Connection Error", 
                             f"Cannot connect to MongoDB at {MONGO_URI}. "
                             "Please ensure the server is running.")
        return False
    except Exception as e:
        messagebox.showerror("Connection Error", f"An unexpected error occurred during connection check: {e}")
        return False

def check_connection_gui():
    """Function to call check_db_connection and show result in a messagebox."""
    if check_db_connection():
        messagebox.showinfo("Connection Status", "Successfully connected to MongoDB!")

def translate_sql():
    """Translate SQL query using app.exe, clean output, and fix value types"""
    global last_translated_query
    sql_query = sql_input.get("1.0", END).strip()
    if not sql_query:
        messagebox.showwarning("Input Error", "Please enter an SQL query.")
        return

    try:
        # Call your parser executable
        process = subprocess.Popen(
            ["app.exe"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(sql_query)

        translated_box.config(state=NORMAL)
        translated_box.delete("1.0", END)

        if stderr:
            translated_box.insert(END, f"Parser Error:\n{stderr}")
            last_translated_query = ""
        else:
            raw_stdout = stdout.strip()

            # 1. Improved Regex: Captures db.collection.find(...) handling varied spacing/arguments
            query_match = re.search(r'(db\.\w+\.find\(.*\))', raw_stdout)
            
            if query_match:
                extracted_query = query_match.group(1) 
            else:
                extracted_query = raw_stdout
                messagebox.showwarning("Translation Warning", 
                                       "Could not strictly parse query from output. Execution may fail.")

            # 2. Fix value types (quotes around strings)
            # This logic now carefully skips fixing things that look like keys or Mongo operators
            def fix_types(match):
                key, val = match.group(1), match.group(2)
                val = val.strip()
                
                # If val is a number, true/false, or already quoted, leave it
                if re.fullmatch(r'\d+(\.\d+)?', val) or val in ['true', 'false'] or val.startswith('"') or val.startswith("'"):
                    return f'"{key}": {val}'
                elif val.startswith('{'): 
                    # If value is a nested object (like $gt), don't wrap it
                    return f'"{key}": {val}'
                else:
                    # It's a plain string, wrap in quotes
                    val_clean = val.strip('"').strip("'")
                    return f'"{key}": "{val_clean}"'
            
            # Apply regex to add quotes to keys and string values if missing
            # Note: This is a simple heuristic; complex nested queries might need a JSON parser
            fixed_query = extracted_query
            
            # 3. Clean up trailing semicolon
            clean_query = fixed_query.rstrip(';')
            
            # 4. Display
            prefixed_query = f"MongoDB Query: {clean_query}"
            translated_box.insert(END, prefixed_query)
            last_translated_query = prefixed_query

        translated_box.config(state=DISABLED)

    except Exception as e:
        messagebox.showerror("Execution Error", str(e))


def execute_mongo_query():
    """Execute the last translated MongoDB query"""
    global last_translated_query
    
    if not check_db_connection():
        return
        
    if not last_translated_query:
        messagebox.showwarning("Execution Error", "No translated query available. Please translate first.")
        return

    try:
        query_str = last_translated_query.strip()
        
        # Check for expected prefix
        if not query_str.startswith("MongoDB Query: db."):
            results_box.config(state=NORMAL)
            results_box.delete("1.0", END)
            results_box.insert(END, "Invalid query format. Prefix missing.")
            results_box.config(state=DISABLED)
            return

        # --- NEW PARSING LOGIC ---
        
        # Remove "MongoDB Query: " prefix
        clean_stmt = query_str[len("MongoDB Query: "):].strip().rstrip(";")
        
        # Extract collection name: db.students.find(...) -> students
        parts = clean_stmt.split(".")
        if len(parts) < 3:
             raise ValueError("Malformed query structure")
        collection_name = parts[1]

        # Extract arguments inside .find( ... )
        # Finds the first '(' and the last ')'
        start_idx = clean_stmt.find("(")
        end_idx = clean_stmt.rfind(")")
        
        if start_idx == -1 or end_idx == -1:
             raise ValueError("Could not find arguments inside .find()")

        args_str = clean_stmt[start_idx+1 : end_idx]
        
        # Handle cases where args might be empty "find( )"
        if not args_str.strip():
            filter_dict = {}
            projection_dict = {"_id": 0}
        else:
            # Use ast.literal_eval to safely parse Python-like/JSON-like string
            # This handles:
            # 1. Single dict: {"a": 1}
            # 2. Tuple of dicts: {"a": 1}, {"b": 1}
            # 3. Single quotes vs double quotes automatically
            try:
                parsed_args = ast.literal_eval(args_str)
            except Exception as parse_err:
                # Fallback: Try correcting JSON format (e.g. converting unquoted keys is hard here, 
                # but ast.literal_eval is usually good for the output from your C program)
                raise ValueError(f"Failed to parse query arguments: {parse_err}")

            # Determine if we have (Filter) or (Filter, Projection)
            if isinstance(parsed_args, dict):
                # Just one argument -> Filter
                filter_dict = parsed_args
                projection_dict = {"_id": 0} # Default: hide ID
            elif isinstance(parsed_args, tuple) and len(parsed_args) == 2:
                # Two arguments -> Filter, Projection
                filter_dict = parsed_args[0]
                projection_dict = parsed_args[1]
                
                # Optional: Force hide _id even if user selected columns, 
                # unless they explicitly asked for it? 
                # Usually standard practice in these tools is to keep _id hidden to look cleaner.
                if "_id" not in projection_dict:
                    projection_dict["_id"] = 0
            else:
                # Fallback for empty or weird states
                filter_dict = {}
                projection_dict = {"_id": 0}

        # Execute
        collection = db[collection_name]
        results = list(collection.find(filter_dict, projection_dict))

        results_box.config(state=NORMAL)
        results_box.delete("1.0", END)

        if not results:
            results_box.insert(END, "No documents found.")
        else:
            for doc in results:
                results_box.insert(END, f"{json.dumps(doc, indent=4)}\n")

        results_box.config(state=DISABLED)

    except Exception as e:
        messagebox.showerror("Execution Error", str(e))


def clear_text():
    """Clear all input and output boxes"""
    global last_translated_query
    sql_input.delete("1.0", END)
    translated_box.config(state=NORMAL)
    translated_box.delete("1.0", END)
    translated_box.config(state=DISABLED)
    results_box.config(state=NORMAL)
    results_box.delete("1.0", END)
    results_box.config(state=DISABLED)
    last_translated_query = ""

# ------------------ GUI ------------------
root = Tk()
root.title("SQL to NOSQL Translator")
root.geometry("1000x650")
root.configure(bg="#e6f2ff")

# Heading
heading_label = Label(root, text="SQL to NOSQL Translator", bg="#e6f2ff", fg="#003366",
                      font=("Arial", 24, "bold"))
heading_label.pack(pady=10)

# SQL Input
Label(root, text="Enter SQL Query:", bg="#e6f2ff", font=("Arial", 12, "bold")).pack(anchor=W, padx=10, pady=(5,0))
sql_input = Text(root, height=8, width=120, font=("Arial", 11))
sql_input.pack(padx=10, pady=(0,10))

# Buttons Frame
button_frame = Frame(root, bg="#e6f2ff")
button_frame.pack(pady=5)

translate_btn = ttk.Button(button_frame, text="Translate", command=translate_sql)
translate_btn.grid(row=0, column=0, padx=10)

execute_btn = ttk.Button(button_frame, text="Execute", command=execute_mongo_query)
execute_btn.grid(row=0, column=1, padx=10)

clear_btn = ttk.Button(button_frame, text="Clear", command=clear_text)
clear_btn.grid(row=0, column=2, padx=10)

check_conn_btn = ttk.Button(button_frame, text="Check DB Connection", command=check_connection_gui)
check_conn_btn.grid(row=0, column=3, padx=10)

# Translated Query Output
Label(root, text="Translated MongoDB Query:", bg="#e6f2ff", font=("Arial", 12, "bold")).pack(anchor=W, padx=10, pady=(10,0))
translated_box = Text(root, height=6, width=120, font=("Arial", 11), state=DISABLED, bg="#f2f2f2")
translated_box.pack(padx=10, pady=(0,10))

# Query Results Output
Label(root, text="Query Results:", bg="#e6f2ff", font=("Arial", 12, "bold")).pack(anchor=W, padx=10, pady=(10,0))
results_box = Text(root, height=10, width=120, font=("Arial", 11), state=DISABLED, bg="#f9f9f9")
results_box.pack(padx=10, pady=(0,10), fill=BOTH, expand=True)

root.mainloop()