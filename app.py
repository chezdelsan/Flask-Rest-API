from flask import Flask, request, jsonify

app = Flask(__name__)

# In-memory "database"
TODOS = {}
NEXT_ID = 1


def make_todo(title, is_done=False, priority=1):
    """Helper to create a todo dict."""
    global NEXT_ID
    todo_id = NEXT_ID
    NEXT_ID += 1
    return {
        "id": todo_id,
        "title": title,
        "is_done": bool(is_done),
        "priority": int(priority),
        "position": todo_id,  # simple ordering field
    }


def get_todo_or_404(todo_id: int):
    todo = TODOS.get(todo_id)
    if not todo:
        return jsonify({"error": "Todo not found"}), 404
    return todo


# ---------- 2× GET ----------

@app.get("/health")
def health_check():
    """
    Simple health check endpoint.
    GET /health
    """
    return jsonify({"status": "ok", "service": "todo-api"}), 200


@app.get("/todos")
def list_todos():
    """
    List todos with optional status filter.
    GET /todos?status=all|open|done
    """
    status = request.args.get("status", "all")
    todos = list(TODOS.values())

    if status == "open":
        todos = [t for t in todos if not t["is_done"]]
    elif status == "done":
        todos = [t for t in todos if t["is_done"]]
    # else "all"

    # Sort by position
    todos.sort(key=lambda t: t["position"])
    return jsonify(todos), 200


# ---------- 2× POST ----------

@app.post("/todos")
def create_todo():
    """
    Create a single todo.
    POST /todos
    JSON body: { "title": "...", "is_done": false, "priority": 1 }
    """
    data = request.get_json(silent=True) or {}
    title = data.get("title")

    if not title:
        return jsonify({"error": "Field 'title' is required"}), 400

    todo = make_todo(
        title=title,
        is_done=data.get("is_done", False),
        priority=data.get("priority", 1),
    )
    TODOS[todo["id"]] = todo
    return jsonify(todo), 201


@app.post("/todos/bulk")
def create_todos_bulk():
    """
    Bulk create todos.
    POST /todos/bulk
    JSON body: { "items": [ { "title": "...", "is_done": false, "priority": 1 }, ... ] }
    """
    data = request.get_json(silent=True) or {}
    items = data.get("items")
    if not isinstance(items, list):
        return jsonify({"error": "Field 'items' must be a list of todos"}), 400

    created = []
    for item in items:
        title = item.get("title")
        if not title:
            # Skip invalid entries
            continue
        todo = make_todo(
            title=title,
            is_done=item.get("is_done", False),
            priority=item.get("priority", 1),
        )
        TODOS[todo["id"]] = todo
        created.append(todo)

    return jsonify({"created": created, "count": len(created)}), 201


# ---------- 2× PUT ----------

@app.put("/todos/<int:todo_id>")
def replace_todo(todo_id):
    """
    Full replace of a todo (idempotent).
    PUT /todos/<id>
    JSON body: { "title": "...", "is_done": bool, "priority": int }
    """
    existing = get_todo_or_404(todo_id)
    if isinstance(existing, tuple):  # error response
        return existing

    data = request.get_json(silent=True) or {}
    required_fields = ["title", "is_done", "priority"]
    if not all(field in data for field in required_fields):
        return jsonify({"error": f"Fields {required_fields} are required"}), 400

    # Keep the existing position
    position = existing["position"]

    updated = {
        "id": todo_id,
        "title": data["title"],
        "is_done": bool(data["is_done"]),
        "priority": int(data["priority"]),
        "position": position,
    }
    TODOS[todo_id] = updated
    return jsonify(updated), 200


@app.put("/todos/<int:todo_id>/status")
def put_todo_status(todo_id):
    """
    Idempotently set status of a todo.
    PUT /todos/<id>/status
    JSON body: { "is_done": bool }
    """
    existing = get_todo_or_404(todo_id)
    if isinstance(existing, tuple):
        return existing

    data = request.get_json(silent=True) or {}
    if "is_done" not in data:
        return jsonify({"error": "Field 'is_done' is required"}), 400

    existing["is_done"] = bool(data["is_done"])
    TODOS[todo_id] = existing
    return jsonify(existing), 200


# ---------- 2× PATCH ----------

@app.patch("/todos/<int:todo_id>")
def patch_todo(todo_id):
    """
    Partial update of a todo.
    PATCH /todos/<id>
    JSON body: any subset of { "title", "is_done", "priority" }
    """
    existing = get_todo_or_404(todo_id)
    if isinstance(existing, tuple):
        return existing

    data = request.get_json(silent=True) or {}
    allowed_fields = {"title", "is_done", "priority"}

    if not any(field in data for field in allowed_fields):
        return jsonify({"error": f"At least one of {list(allowed_fields)} is required"}), 400

    for field in allowed_fields:
        if field in data:
            if field == "is_done":
                existing[field] = bool(data[field])
            elif field == "priority":
                existing[field] = int(data[field])
            else:
                existing[field] = data[field]

    TODOS[todo_id] = existing
    return jsonify(existing), 200


@app.patch("/todos/reorder")
def reorder_todos():
    """
    Reorder todos in bulk by id.
    PATCH /todos/reorder
    JSON body: { "order": [3, 1, 2] }
    """
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, list):
        return jsonify({"error": "Field 'order' must be a list of ids"}), 400

    # Validate all ids exist
    missing = [tid for tid in order if tid not in TODOS]
    if missing:
        return jsonify({"error": f"Unknown ids in 'order': {missing}"}), 400

    # Apply new positions
    for idx, tid in enumerate(order, start=1):
        TODOS[tid]["position"] = idx

    # For any todos not mentioned, put them after
    remaining = [t for t in TODOS.values() if t["id"] not in order]
    current_pos = len(order) + 1
    for t in remaining:
        t["position"] = current_pos
        current_pos += 1

    todos_sorted = sorted(TODOS.values(), key=lambda t: t["position"])
    return jsonify(todos_sorted), 200


# ---------- 2× DELETE ----------

@app.delete("/todos/<int:todo_id>")
def delete_todo(todo_id):
    """
    Delete a single todo.
    DELETE /todos/<id>
    """
    existing = TODOS.pop(todo_id, None)
    if not existing:
        return jsonify({"error": "Todo not found"}), 404
    return jsonify({"deleted_id": todo_id}), 200


@app.delete("/todos")
def delete_many_todos():
    """
    Delete many (or all) todos.
    DELETE /todos?completed_only=true|false
    - if completed_only=true: delete only todos where is_done=true
    - otherwise: delete all
    """
    completed_only = request.args.get("completed_only", "false").lower() == "true"

    if completed_only:
        to_delete = [tid for tid, t in TODOS.items() if t["is_done"]]
        for tid in to_delete:
            TODOS.pop(tid, None)
        return jsonify({"deleted_ids": to_delete, "completed_only": True}), 200
    else:
        deleted_ids = list(TODOS.keys())
        TODOS.clear()
        return jsonify({"deleted_ids": deleted_ids, "completed_only": False}), 200


if __name__ == "__main__":
    # In real production you'd use gunicorn/uwsgi, but this is fine for dev.
    app.run(debug=True)
