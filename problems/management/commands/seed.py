import os
import random
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from problems.models import Comment, Like, Problem, ProblemFile, UpdateProblem
from users.models import SocialAccount, Submission, User, UserLocation

TIMEZONES = [
    'UTC', 'Asia/Tokyo', 'Asia/Tashkent', 'Europe/Berlin', 'Europe/London',
    'America/New_York', 'America/Los_Angeles', 'Australia/Sydney',
]

USERNAMES = [
    'alice', 'bob', 'carol', 'dave', 'erin', 'frank', 'grace', 'heidi', 'ivan', 'judy',
]

TIME_REQUIRED = {'easy': 30, 'medium': 60, 'hard': 120}


def django_project(apps, urls, rest_framework=False):
    installed = ['django.contrib.auth', 'django.contrib.contenttypes', *apps]
    if rest_framework:
        installed.append('rest_framework')
    settings_py = (
        'from pathlib import Path\n'
        '\n'
        'BASE_DIR = Path(__file__).resolve().parent.parent\n'
        'SECRET_KEY = "local-dev-only"\n'
        'DEBUG = True\n'
        'ALLOWED_HOSTS = ["localhost", "127.0.0.1"]\n'
        'ROOT_URLCONF = "config.urls"\n'
        'USE_TZ = True\n'
        'DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"\n'
        f'INSTALLED_APPS = {installed!r}\n'
        'MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]\n'
        'DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}\n'
    )
    if rest_framework:
        settings_py += (
            'REST_FRAMEWORK = {\n'
            '    "DEFAULT_AUTHENTICATION_CLASSES": [],\n'
            '    "DEFAULT_PERMISSION_CLASSES": [],\n'
            '    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],\n'
            '}\n'
        )
    requirements = 'Django>=6.1\n' + ('djangorestframework>=3.18\n' if rest_framework else '')
    return {
        'requirements.txt': requirements,
        'manage.py': (
            'import os\n'
            'import sys\n'
            '\n'
            'if __name__ == "__main__":\n'
            '    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")\n'
            '    from django.core.management import execute_from_command_line\n'
            '\n'
            '    execute_from_command_line(sys.argv)\n'
        ),
        'config/__init__.py': '',
        'config/settings.py': settings_py,
        'config/urls.py': urls,
    }


def vite_app(name, main_file, main_source):
    return {
        'package.json': (
            '{\n'
            f'  "name": "{name}",\n'
            '  "private": true,\n'
            '  "type": "module",\n'
            '  "scripts": {"dev": "vite", "build": "vite build"},\n'
            '  "dependencies": {"react": "19.3.0", "react-dom": "19.3.0"},\n'
            '  "devDependencies": {"vite": "8.3.0", "@vitejs/plugin-react": "6.1.1"}\n'
            '}\n'
        ),
        'index.html': (
            '<!doctype html>\n'
            '<html lang="en">\n'
            '  <body>\n'
            '    <div id="root"></div>\n'
            f'    <script type="module" src="/src/{main_file}"></script>\n'
            '  </body>\n'
            '</html>\n'
        ),
        'vite.config.js': (
            'import { defineConfig } from "vite";\n'
            'import react from "@vitejs/plugin-react";\n'
            '\n'
            'export default defineConfig({ plugins: [react()] });\n'
        ),
        f'src/{main_file}': main_source,
    }


LOGIN_FILES = {
    **django_project(
        ['accounts'],
        'from django.urls import path\n'
        '\n'
        'from accounts.views import LoginView\n'
        '\n'
        'urlpatterns = [path("login/", LoginView.as_view())]\n',
        rest_framework=True,
    ),
    'README.md': (
        '# Auth service\n'
        '\n'
        '`POST /login/` with `{"username": ..., "password": ...}`.\n'
        '\n'
        'A wrong password or an unknown user crashes the view with a 500. It should return 401.\n'
        'A request that is missing the username or the password should return 400.\n'
        '\n'
        'A demo user `alice` / `wonderland` is created by a migration.\n'
        '\n'
        '```\n'
        'pip install -r requirements.txt\n'
        'python manage.py migrate\n'
        'python manage.py runserver\n'
        '```\n'
    ),
    'accounts/__init__.py': '',
    'accounts/migrations/__init__.py': '',
    'accounts/migrations/0001_demo_user.py': (
        'from django.contrib.auth.hashers import make_password\n'
        'from django.db import migrations\n'
        '\n'
        '\n'
        'def create_demo_user(apps, schema_editor):\n'
        '    User = apps.get_model("auth", "User")\n'
        '    User.objects.create(username="alice", password=make_password("wonderland"))\n'
        '\n'
        '\n'
        'class Migration(migrations.Migration):\n'
        '    dependencies = [("auth", "0012_alter_user_first_name_max_length")]\n'
        '\n'
        '    operations = [migrations.RunPython(create_demo_user, migrations.RunPython.noop)]\n'
    ),
    'accounts/views.py': (
        'from django.contrib.auth import authenticate\n'
        'from rest_framework.response import Response\n'
        'from rest_framework.views import APIView\n'
        '\n'
        '\n'
        'class LoginView(APIView):\n'
        '    def post(self, request):\n'
        '        user = authenticate(username=request.data["username"], password=request.data["password"])\n'
        '        return Response({"id": user.id, "username": user.username})\n'
    ),
}

LOGIN_HIDDEN = {
    'tests/test_hidden_login.py': (
        'def test_correct_password_logs_in(client):\n'
        '    response = client.post("/login/", json={"username": "alice", "password": "wonderland"})\n'
        '    assert response.status_code == 200\n'
        '    assert response.json()["username"] == "alice"\n'
        '\n'
        '\n'
        'def test_wrong_password_returns_401(client):\n'
        '    response = client.post("/login/", json={"username": "alice", "password": "nope"})\n'
        '    assert response.status_code == 401\n'
        '\n'
        '\n'
        'def test_unknown_user_returns_401(client):\n'
        '    response = client.post("/login/", json={"username": "mallory", "password": "wonderland"})\n'
        '    assert response.status_code == 401\n'
        '\n'
        '\n'
        'def test_missing_password_returns_400(client):\n'
        '    response = client.post("/login/", json={"username": "alice"})\n'
        '    assert response.status_code == 400\n'
    ),
}

NOTES_FILES = {
    **django_project(
        ['notes'],
        'from django.urls import path\n'
        '\n'
        'from notes import views\n'
        '\n'
        'urlpatterns = [\n'
        '    path("notes/", views.note_list),\n'
        '    path("notes/<int:note_id>/", views.note_detail),\n'
        ']\n',
    ),
    'README.md': (
        '# Notes\n'
        '\n'
        'Support keeps restoring notes from backups because `DELETE /notes/<id>/` removes the row.\n'
        '\n'
        'Add soft delete:\n'
        '\n'
        '- `DELETE /notes/<id>/` sets a `deleted_at` timestamp instead of deleting the row, and still returns 204.\n'
        '- Deleted notes no longer show up in `GET /notes/`, and `GET /notes/<id>/` returns 404 for them.\n'
        '- New endpoint `GET /notes/trash/` lists deleted notes (`id`, `body`, `deleted_at`), and nothing else.\n'
        '\n'
        'Remember to include the migration for the new field.\n'
    ),
    'notes/__init__.py': '',
    'notes/models.py': (
        'from django.db import models\n'
        '\n'
        '\n'
        'class Note(models.Model):\n'
        '    body = models.TextField()\n'
        '    created_at = models.DateTimeField(auto_now_add=True)\n'
    ),
    'notes/migrations/__init__.py': '',
    'notes/migrations/0001_initial.py': (
        'from django.db import migrations, models\n'
        '\n'
        '\n'
        'class Migration(migrations.Migration):\n'
        '    initial = True\n'
        '\n'
        '    dependencies = []\n'
        '\n'
        '    operations = [\n'
        '        migrations.CreateModel(\n'
        '            name="Note",\n'
        '            fields=[\n'
        '                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),\n'
        '                ("body", models.TextField()),\n'
        '                ("created_at", models.DateTimeField(auto_now_add=True)),\n'
        '            ],\n'
        '        ),\n'
        '    ]\n'
    ),
    'notes/views.py': (
        'import json\n'
        '\n'
        'from django.http import HttpResponse, JsonResponse\n'
        'from django.shortcuts import get_object_or_404\n'
        'from django.views.decorators.csrf import csrf_exempt\n'
        'from django.views.decorators.http import require_http_methods\n'
        '\n'
        'from .models import Note\n'
        '\n'
        '\n'
        'def serialize(note):\n'
        '    return {"id": note.id, "body": note.body, "created_at": note.created_at.isoformat()}\n'
        '\n'
        '\n'
        '@csrf_exempt\n'
        '@require_http_methods(["GET", "POST"])\n'
        'def note_list(request):\n'
        '    if request.method == "POST":\n'
        '        body = json.loads(request.body or "{}").get("body", "")\n'
        '        if not body:\n'
        '            return JsonResponse({"detail": "body is required"}, status=400)\n'
        '        note = Note.objects.create(body=body)\n'
        '        return JsonResponse(serialize(note), status=201)\n'
        '    return JsonResponse([serialize(note) for note in Note.objects.order_by("id")], safe=False)\n'
        '\n'
        '\n'
        '@csrf_exempt\n'
        '@require_http_methods(["GET", "DELETE"])\n'
        'def note_detail(request, note_id):\n'
        '    note = get_object_or_404(Note, pk=note_id)\n'
        '    if request.method == "DELETE":\n'
        '        note.delete()\n'
        '        return HttpResponse(status=204)\n'
        '    return JsonResponse(serialize(note))\n'
    ),
}

NOTES_HIDDEN = {
    'tests/test_hidden_soft_delete.py': (
        'def create(client, body):\n'
        '    response = client.post("/notes/", json={"body": body})\n'
        '    assert response.status_code == 201\n'
        '    return response.json()["id"]\n'
        '\n'
        '\n'
        'def test_deleted_note_is_hidden_from_the_list(client):\n'
        '    keep, drop = create(client, "keep"), create(client, "drop")\n'
        '    assert client.delete(f"/notes/{drop}/").status_code == 204\n'
        '    ids = [note["id"] for note in client.get("/notes/").json()]\n'
        '    assert keep in ids and drop not in ids\n'
        '\n'
        '\n'
        'def test_deleted_note_detail_returns_404(client):\n'
        '    note_id = create(client, "gone")\n'
        '    client.delete(f"/notes/{note_id}/")\n'
        '    assert client.get(f"/notes/{note_id}/").status_code == 404\n'
        '\n'
        '\n'
        'def test_deleted_note_is_kept_in_the_trash(client):\n'
        '    note_id = create(client, "recoverable")\n'
        '    client.delete(f"/notes/{note_id}/")\n'
        '    trash = {note["id"]: note for note in client.get("/notes/trash/").json()}\n'
        '    assert trash[note_id]["body"] == "recoverable"\n'
        '    assert trash[note_id]["deleted_at"]\n'
        '\n'
        '\n'
        'def test_trash_does_not_list_live_notes(client):\n'
        '    note_id = create(client, "still here")\n'
        '    ids = [note["id"] for note in client.get("/notes/trash/").json()]\n'
        '    assert note_id not in ids\n'
    ),
}

INVENTORY_FILES = {
    **django_project(
        ['inventory'],
        'from django.urls import path\n'
        '\n'
        'from inventory import views\n'
        '\n'
        'urlpatterns = [\n'
        '    path("items/", views.ItemListView.as_view()),\n'
        '    path("items/<int:item_id>/", views.ItemDetailView.as_view()),\n'
        '    path("items/<int:item_id>/reserve/", views.ReserveView.as_view()),\n'
        ']\n',
        rest_framework=True,
    ),
    'README.md': (
        '# Inventory\n'
        '\n'
        'During a flash sale we sold 40 units of an item that had 5 in stock.\n'
        '\n'
        '- `POST /items/` with `{"name": ..., "stock": ...}` creates an item.\n'
        '- `POST /items/<id>/reserve/` with `{"qty": ...}` returns 200 when the stock was reserved, 409 when there is not enough.\n'
        '\n'
        'Concurrent reservations must never reserve more than the stock. A quantity below 1 must be rejected with 400.\n'
        '\n'
        '`notify_warehouse` stands in for a slow HTTP call to the warehouse service (about 100ms) and has to stay.\n'
        'The app runs on SQLite, so `select_for_update` will not help here.\n'
    ),
    'inventory/__init__.py': '',
    'inventory/models.py': (
        'from django.db import models\n'
        '\n'
        '\n'
        'class Item(models.Model):\n'
        '    name = models.CharField(max_length=100)\n'
        '    stock = models.PositiveIntegerField(default=0)\n'
    ),
    'inventory/migrations/__init__.py': '',
    'inventory/migrations/0001_initial.py': (
        'from django.db import migrations, models\n'
        '\n'
        '\n'
        'class Migration(migrations.Migration):\n'
        '    initial = True\n'
        '\n'
        '    dependencies = []\n'
        '\n'
        '    operations = [\n'
        '        migrations.CreateModel(\n'
        '            name="Item",\n'
        '            fields=[\n'
        '                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),\n'
        '                ("name", models.CharField(max_length=100)),\n'
        '                ("stock", models.PositiveIntegerField(default=0)),\n'
        '            ],\n'
        '        ),\n'
        '    ]\n'
    ),
    'inventory/warehouse.py': (
        'import time\n'
        '\n'
        '\n'
        'def notify_warehouse(item_id, qty):\n'
        '    time.sleep(0.1)\n'
    ),
    'inventory/services.py': (
        'from .models import Item\n'
        'from .warehouse import notify_warehouse\n'
        '\n'
        '\n'
        'def reserve(item_id, qty):\n'
        '    item = Item.objects.get(pk=item_id)\n'
        '    if item.stock < qty:\n'
        '        return False\n'
        '    notify_warehouse(item_id, qty)\n'
        '    item.stock -= qty\n'
        '    item.save()\n'
        '    return True\n'
    ),
    'inventory/views.py': (
        'from django.shortcuts import get_object_or_404\n'
        'from rest_framework import serializers, status\n'
        'from rest_framework.response import Response\n'
        'from rest_framework.views import APIView\n'
        '\n'
        'from .models import Item\n'
        'from .services import reserve\n'
        '\n'
        '\n'
        'class ItemSerializer(serializers.ModelSerializer):\n'
        '    class Meta:\n'
        '        model = Item\n'
        '        fields = ["id", "name", "stock"]\n'
        '\n'
        '\n'
        'class ReservationSerializer(serializers.Serializer):\n'
        '    qty = serializers.IntegerField()\n'
        '\n'
        '\n'
        'class ItemListView(APIView):\n'
        '    def post(self, request):\n'
        '        serializer = ItemSerializer(data=request.data)\n'
        '        serializer.is_valid(raise_exception=True)\n'
        '        serializer.save()\n'
        '        return Response(serializer.data, status=status.HTTP_201_CREATED)\n'
        '\n'
        '\n'
        'class ItemDetailView(APIView):\n'
        '    def get(self, request, item_id):\n'
        '        return Response(ItemSerializer(get_object_or_404(Item, pk=item_id)).data)\n'
        '\n'
        '\n'
        'class ReserveView(APIView):\n'
        '    def post(self, request, item_id):\n'
        '        get_object_or_404(Item, pk=item_id)\n'
        '        serializer = ReservationSerializer(data=request.data)\n'
        '        serializer.is_valid(raise_exception=True)\n'
        '        if not reserve(item_id, serializer.validated_data["qty"]):\n'
        '            return Response({"detail": "Not enough stock"}, status=status.HTTP_409_CONFLICT)\n'
        '        return Response({"reserved": True})\n'
    ),
}

INVENTORY_HELPERS = (
    'def create_item(client, stock):\n'
    '    response = client.post("/items/", json={"name": "Widget", "stock": stock})\n'
    '    assert response.status_code == 201\n'
    '    return response.json()["id"]\n'
    '\n'
    '\n'
    'def stock_of(client, item_id):\n'
    '    return client.get(f"/items/{item_id}/").json()["stock"]\n'
)

INVENTORY_HIDDEN = {
    'tests/test_hidden_reserve.py': (
        'from concurrent.futures import ThreadPoolExecutor\n'
        '\n'
        'import requests\n'
        '\n'
        '\n'
        + INVENTORY_HELPERS +
        '\n'
        '\n'
        'def test_reservation_reduces_stock(client):\n'
        '    item_id = create_item(client, 5)\n'
        '    assert client.post(f"/items/{item_id}/reserve/", json={"qty": 2}).status_code == 200\n'
        '    assert stock_of(client, item_id) == 3\n'
        '\n'
        '\n'
        'def test_reserving_more_than_the_stock_is_rejected(client):\n'
        '    item_id = create_item(client, 1)\n'
        '    assert client.post(f"/items/{item_id}/reserve/", json={"qty": 2}).status_code == 409\n'
        '    assert stock_of(client, item_id) == 1\n'
        '\n'
        '\n'
        'def test_concurrent_reservations_never_oversell(client, app_url):\n'
        '    item_id = create_item(client, 5)\n'
        '\n'
        '    def reserve_one(_):\n'
        '        return requests.post(\n'
        '            f"{app_url}/items/{item_id}/reserve/", json={"qty": 1},\n'
        '            headers={"Host": "localhost"}, timeout=30,\n'
        '        ).status_code\n'
        '\n'
        '    with ThreadPoolExecutor(max_workers=10) as pool:\n'
        '        codes = list(pool.map(reserve_one, range(10)))\n'
        '\n'
        '    assert codes.count(200) == 5\n'
        '    assert codes.count(409) == 5\n'
        '    assert stock_of(client, item_id) == 0\n'
    ),
    'tests/test_hidden_reserve_edge.py': (
        INVENTORY_HELPERS +
        '\n'
        '\n'
        'def test_zero_quantity_is_rejected(client):\n'
        '    item_id = create_item(client, 3)\n'
        '    assert client.post(f"/items/{item_id}/reserve/", json={"qty": 0}).status_code == 400\n'
        '\n'
        '\n'
        'def test_negative_quantity_is_rejected_and_stock_is_unchanged(client):\n'
        '    item_id = create_item(client, 3)\n'
        '    assert client.post(f"/items/{item_id}/reserve/", json={"qty": -3}).status_code == 400\n'
        '    assert stock_of(client, item_id) == 3\n'
    ),
}

TODO_FILES = {
    **vite_app(
        'todo-app', 'main.jsx',
        'import { createRoot } from "react-dom/client";\n'
        'import App from "./App.jsx";\n'
        '\n'
        'createRoot(document.getElementById("root")).render(<App />);\n',
    ),
    'README.md': (
        '# Todo app\n'
        '\n'
        'With a few hundred todos the search box lags, because every keystroke re-renders every item.\n'
        '\n'
        'Typing in the search box must not re-render items that stay visible, and toggling one todo must\n'
        're-render only that todo. Filtering and toggling must keep working.\n'
        '\n'
        '`TodoItem` calls `logRender` on each render; QA reads `window.renderLog` to count renders. Keep that call.\n'
        '\n'
        '```\n'
        'npm install\n'
        'npm run dev\n'
        '```\n'
    ),
    'src/renderLog.js': (
        'export function logRender(id) {\n'
        '  window.renderLog = window.renderLog || [];\n'
        '  window.renderLog.push(id);\n'
        '}\n'
    ),
    'src/App.jsx': (
        'import { useState } from "react";\n'
        'import TodoList from "./TodoList.jsx";\n'
        '\n'
        'const INITIAL_TODOS = [\n'
        '  { id: 1, title: "Buy milk", done: false },\n'
        '  { id: 2, title: "Walk the dog", done: false },\n'
        '  { id: 3, title: "Write the weekly report", done: false },\n'
        '  { id: 4, title: "Water the plants", done: true },\n'
        '];\n'
        '\n'
        'export default function App() {\n'
        '  const [todos, setTodos] = useState(INITIAL_TODOS);\n'
        '  const [query, setQuery] = useState("");\n'
        '\n'
        '  function toggle(id) {\n'
        '    setTodos((current) => current.map((t) => (t.id === id ? { ...t, done: !t.done } : t)));\n'
        '  }\n'
        '\n'
        '  return (\n'
        '    <main>\n'
        '      <input aria-label="Search" value={query} onChange={(e) => setQuery(e.target.value)} />\n'
        '      <TodoList todos={todos} query={query} onToggle={toggle} />\n'
        '    </main>\n'
        '  );\n'
        '}\n'
    ),
    'src/TodoList.jsx': (
        'import TodoItem from "./TodoItem.jsx";\n'
        '\n'
        'export default function TodoList({ todos, query, onToggle }) {\n'
        '  const visible = todos.filter((t) => t.title.toLowerCase().includes(query.toLowerCase()));\n'
        '  return (\n'
        '    <ul>\n'
        '      {visible.map((t) => (\n'
        '        <TodoItem key={t.id} todo={t} onToggle={() => onToggle(t.id)} />\n'
        '      ))}\n'
        '    </ul>\n'
        '  );\n'
        '}\n'
    ),
    'src/TodoItem.jsx': (
        'import { logRender } from "./renderLog.js";\n'
        '\n'
        'export default function TodoItem({ todo, onToggle }) {\n'
        '  logRender(todo.id);\n'
        '  return (\n'
        '    <li>\n'
        '      <label>\n'
        '        <input type="checkbox" checked={todo.done} onChange={onToggle} />\n'
        '        {todo.title}\n'
        '      </label>\n'
        '    </li>\n'
        '  );\n'
        '}\n'
    ),
}

TODO_HIDDEN = {
    'tests/test_hidden_todo_list.py': (
        'from playwright.sync_api import expect\n'
        '\n'
        '\n'
        'def open_app(page):\n'
        '    page.goto("/")\n'
        '    expect(page.get_by_role("listitem")).to_have_count(4)\n'
        '    return len(page.evaluate("window.renderLog"))\n'
        '\n'
        '\n'
        'def test_every_item_renders_on_load(page):\n'
        '    open_app(page)\n'
        '    assert sorted(page.evaluate("window.renderLog")) == [1, 2, 3, 4]\n'
        '\n'
        '\n'
        'def test_search_filters_the_list(page):\n'
        '    open_app(page)\n'
        '    page.get_by_label("Search").fill("milk")\n'
        '    expect(page.get_by_role("listitem")).to_have_text(["Buy milk"])\n'
        '\n'
        '\n'
        'def test_typing_does_not_rerender_visible_items(page):\n'
        '    before = open_app(page)\n'
        '    page.get_by_label("Search").press_sequentially("w")\n'
        '    expect(page.get_by_role("listitem")).to_have_count(3)\n'
        '    assert page.evaluate("window.renderLog")[before:] == []\n'
        '\n'
        '\n'
        'def test_toggling_rerenders_only_that_item(page):\n'
        '    before = open_app(page)\n'
        '    page.get_by_label("Buy milk").check()\n'
        '    expect(page.get_by_label("Buy milk")).to_be_checked()\n'
        '    assert page.evaluate("window.renderLog")[before:] == [1]\n'
    ),
}

PROFILE_FILES = {
    **vite_app(
        'profile-form', 'main.tsx',
        'import { createRoot } from "react-dom/client";\n'
        'import { ProfileForm } from "./ProfileForm";\n'
        '\n'
        'createRoot(document.getElementById("root")!).render(<ProfileForm />);\n',
    ),
    'README.md': (
        '# Profile form\n'
        '\n'
        'Users double click Save and we create two profiles.\n'
        '\n'
        'While a save is in flight the Save button must be disabled, so a double click sends one request.\n'
        'Once the save finishes the button must work again.\n'
        '\n'
        '`src/api.ts` is a stub of the real API client: it waits 500ms and records each call in `window.saveCalls`.\n'
    ),
    'src/api.ts': (
        'export interface Profile {\n'
        '  name: string;\n'
        '}\n'
        '\n'
        'declare global {\n'
        '  interface Window {\n'
        '    saveCalls: Profile[];\n'
        '  }\n'
        '}\n'
        '\n'
        'window.saveCalls = [];\n'
        '\n'
        'export async function saveProfile(profile: Profile): Promise<void> {\n'
        '  window.saveCalls.push(profile);\n'
        '  await new Promise((resolve) => setTimeout(resolve, 500));\n'
        '}\n'
    ),
    'src/ProfileForm.tsx': (
        'import { useState, type FormEvent } from "react";\n'
        'import { saveProfile } from "./api";\n'
        '\n'
        'export function ProfileForm() {\n'
        '  const [name, setName] = useState("");\n'
        '  const [status, setStatus] = useState("");\n'
        '\n'
        '  async function handleSubmit(event: FormEvent) {\n'
        '    event.preventDefault();\n'
        '    await saveProfile({ name });\n'
        '    setStatus("Saved");\n'
        '  }\n'
        '\n'
        '  return (\n'
        '    <form onSubmit={handleSubmit}>\n'
        '      <label>\n'
        '        Name\n'
        '        <input value={name} onChange={(e) => setName(e.target.value)} />\n'
        '      </label>\n'
        '      <button type="submit">Save</button>\n'
        '      <p role="status">{status}</p>\n'
        '    </form>\n'
        '  );\n'
        '}\n'
    ),
}

PROFILE_HIDDEN = {
    'tests/test_hidden_profile_form.py': (
        'from playwright.sync_api import expect\n'
        '\n'
        '\n'
        'def fill_name(page):\n'
        '    page.goto("/")\n'
        '    page.get_by_label("Name").fill("Ada")\n'
        '\n'
        '\n'
        'def test_double_click_saves_once(page):\n'
        '    fill_name(page)\n'
        '    page.get_by_role("button").dblclick()\n'
        '    expect(page.get_by_role("status")).to_have_text("Saved")\n'
        '    assert page.evaluate("window.saveCalls.length") == 1\n'
        '\n'
        '\n'
        'def test_button_is_disabled_while_saving(page):\n'
        '    fill_name(page)\n'
        '    page.get_by_role("button").click()\n'
        '    expect(page.get_by_role("button")).to_be_disabled()\n'
        '\n'
        '\n'
        'def test_button_works_again_after_saving(page):\n'
        '    fill_name(page)\n'
        '    page.get_by_role("button").click()\n'
        '    expect(page.get_by_role("status")).to_have_text("Saved")\n'
        '    expect(page.get_by_role("button")).to_be_enabled()\n'
        '    page.get_by_role("button").click()\n'
        '    page.wait_for_function("window.saveCalls.length === 2")\n'
    ),
}

PRODUCT_PAGE_FILES = {
    'package.json': (
        '{\n'
        '  "name": "shop",\n'
        '  "private": true,\n'
        '  "scripts": {"dev": "next dev", "build": "next build", "start": "next start"},\n'
        '  "dependencies": {"next": "16.3.6", "react": "19.3.0", "react-dom": "19.3.0"},\n'
        '  "devDependencies": {"typescript": "5.9.3", "@types/node": "26.6.2", "@types/react": "19.3.0", "@types/react-dom": "19.3.0"}\n'
        '}\n'
    ),
    'tsconfig.json': (
        '{\n'
        '  "compilerOptions": {\n'
        '    "target": "ES2022",\n'
        '    "lib": ["dom", "dom.iterable", "esnext"],\n'
        '    "allowJs": false,\n'
        '    "skipLibCheck": true,\n'
        '    "strict": true,\n'
        '    "noEmit": true,\n'
        '    "esModuleInterop": true,\n'
        '    "module": "esnext",\n'
        '    "moduleResolution": "bundler",\n'
        '    "resolveJsonModule": true,\n'
        '    "isolatedModules": true,\n'
        '    "jsx": "react-jsx",\n'
        '    "incremental": true,\n'
        '    "plugins": [{"name": "next"}]\n'
        '  },\n'
        '  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx"],\n'
        '  "exclude": ["node_modules"]\n'
        '}\n'
    ),
    'README.md': (
        '# Shop\n'
        '\n'
        'Product pages are rendered on every request, and the catalogue service cannot keep up.\n'
        '\n'
        'Make `/products/<id>` static: prerender the known products at build time and revalidate them\n'
        'every 60 seconds. Unknown products must still return 404.\n'
        '\n'
        '```\n'
        'npm install\n'
        'npm run build && npm start\n'
        '```\n'
    ),
    'app/layout.tsx': (
        'export default function RootLayout({ children }: { children: React.ReactNode }) {\n'
        '  return (\n'
        '    <html lang="en">\n'
        '      <body>{children}</body>\n'
        '    </html>\n'
        '  );\n'
        '}\n'
    ),
    'lib/products.ts': (
        'export interface Product {\n'
        '  id: string;\n'
        '  name: string;\n'
        '  price: number;\n'
        '}\n'
        '\n'
        'const PRODUCTS: Product[] = [\n'
        '  { id: "1", name: "Mechanical keyboard", price: 129 },\n'
        '  { id: "2", name: "Standing desk", price: 499 },\n'
        '  { id: "3", name: "Noise-cancelling headphones", price: 249 },\n'
        '];\n'
        '\n'
        'export async function getProduct(id: string): Promise<Product | undefined> {\n'
        '  return PRODUCTS.find((product) => product.id === id);\n'
        '}\n'
        '\n'
        'export async function getProductIds(): Promise<string[]> {\n'
        '  return PRODUCTS.map((product) => product.id);\n'
        '}\n'
    ),
    'app/products/[id]/page.tsx': (
        'import { notFound } from "next/navigation";\n'
        'import { getProduct } from "../../../lib/products";\n'
        '\n'
        'export const dynamic = "force-dynamic";\n'
        '\n'
        'export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {\n'
        '  const { id } = await params;\n'
        '  const product = await getProduct(id);\n'
        '  if (!product) notFound();\n'
        '\n'
        '  return (\n'
        '    <main>\n'
        '      <h1>{product.name}</h1>\n'
        '      <p>${product.price}</p>\n'
        '    </main>\n'
        '  );\n'
        '}\n'
    ),
}

PRODUCT_PAGE_HIDDEN = {
    'tests/test_hidden_product_page.py': (
        'from playwright.sync_api import expect\n'
        '\n'
        '\n'
        'def test_product_page_renders(page):\n'
        '    page.goto("/products/1")\n'
        '    expect(page.get_by_role("heading")).to_have_text("Mechanical keyboard")\n'
        '\n'
        '\n'
        'def test_unknown_product_returns_404(page):\n'
        '    assert page.request.get("/products/999").status == 404\n'
        '\n'
        '\n'
        'def test_known_product_is_prerendered(page):\n'
        '    response = page.request.get("/products/2")\n'
        '    assert response.ok\n'
        '    assert response.headers.get("x-nextjs-prerender") == "1"\n'
        '\n'
        '\n'
        'def test_product_page_revalidates_every_60_seconds(page):\n'
        '    response = page.request.get("/products/3")\n'
        '    assert response.ok\n'
        '    assert "s-maxage=60," in response.headers.get("cache-control", "") + ","\n'
    ),
}

DOCKERFILE_HIDDEN = {
    'tests/test_hidden_dockerfile.py': (
        'def stages(submission_dir):\n'
        '    result = []\n'
        '    for raw in (submission_dir / "Dockerfile").read_text().splitlines():\n'
        '        line = raw.strip()\n'
        '        if not line or line.startswith("#"):\n'
        '            continue\n'
        '        if line.upper().startswith("FROM "):\n'
        '            result.append([line])\n'
        '        elif result:\n'
        '            result[-1].append(line)\n'
        '    return result\n'
        '\n'
        '\n'
        'def instructions(stage, name):\n'
        '    return [line.split(None, 1)[1] for line in stage if line.split(None, 1)[0].upper() == name and " " in line]\n'
        '\n'
        '\n'
        'def test_uses_a_multi_stage_build(submission_dir):\n'
        '    assert len(stages(submission_dir)) >= 2\n'
        '\n'
        '\n'
        'def test_final_stage_runs_as_a_non_root_user(submission_dir):\n'
        '    users = instructions(stages(submission_dir)[-1], "USER")\n'
        '    assert users and users[-1].split(":")[0] not in ("root", "0")\n'
        '\n'
        '\n'
        'def test_final_stage_uses_a_small_base_image(submission_dir):\n'
        '    words = [w for w in stages(submission_dir)[-1][0].split()[1:] if not w.startswith("--")]\n'
        '    assert any(tag in words[0] for tag in ("slim", "alpine", "distroless"))\n'
        '\n'
        '\n'
        'def test_app_still_starts_with_gunicorn(submission_dir):\n'
        '    final = stages(submission_dir)[-1]\n'
        '    commands = instructions(final, "CMD") + instructions(final, "ENTRYPOINT")\n'
        '    assert any("gunicorn" in command for command in commands)\n'
    ),
}

CI_HIDDEN = {
    'tests/test_hidden_ci.py': (
        'import yaml\n'
        '\n'
        '\n'
        'def steps(submission_dir):\n'
        '    workflow = yaml.safe_load((submission_dir / ".github/workflows/ci.yml").read_text())\n'
        '    return [step for job in workflow["jobs"].values() for step in job.get("steps", [])]\n'
        '\n'
        '\n'
        'def commands(submission_dir):\n'
        '    return "\\n".join(str(step.get("run", "")) for step in steps(submission_dir))\n'
        '\n'
        '\n'
        'def caches_npm(step):\n'
        '    uses = str(step.get("uses", ""))\n'
        '    options = step.get("with") or {}\n'
        '    if uses.startswith("actions/setup-node@"):\n'
        '        return options.get("cache") == "npm"\n'
        '    if uses.startswith("actions/cache@"):\n'
        '        return "package-lock.json" in str(options.get("key", ""))\n'
        '    return False\n'
        '\n'
        '\n'
        'def test_dependencies_are_cached_on_the_lock_file(submission_dir):\n'
        '    assert any(caches_npm(step) for step in steps(submission_dir))\n'
        '\n'
        '\n'
        'def test_installs_exactly_what_the_lock_file_says(submission_dir):\n'
        '    run = commands(submission_dir)\n'
        '    assert "npm ci" in run and "npm install" not in run\n'
        '\n'
        '\n'
        'def test_tests_still_run(submission_dir):\n'
        '    run = commands(submission_dir)\n'
        '    assert "npm test" in run or "npm run test" in run\n'
    ),
}

COMPOSE_HIDDEN = {
    'tests/test_hidden_compose.py': (
        'import yaml\n'
        '\n'
        '\n'
        'def services(submission_dir):\n'
        '    return yaml.safe_load((submission_dir / "docker-compose.yml").read_text())["services"]\n'
        '\n'
        '\n'
        'def test_db_has_a_pg_isready_healthcheck(submission_dir):\n'
        '    check = (services(submission_dir)["db"].get("healthcheck") or {}).get("test", "")\n'
        '    assert "pg_isready" in (" ".join(check) if isinstance(check, list) else str(check))\n'
        '\n'
        '\n'
        'def test_app_waits_for_a_healthy_db(submission_dir):\n'
        '    depends_on = services(submission_dir)["app"].get("depends_on")\n'
        '    assert isinstance(depends_on, dict)\n'
        '    assert (depends_on.get("db") or {}).get("condition") == "service_healthy"\n'
        '\n'
        '\n'
        'def test_app_is_still_published_on_port_8000(submission_dir):\n'
        '    ports = [str(port) for port in services(submission_dir)["app"].get("ports", [])]\n'
        '    assert "8000:8000" in ports\n'
    ),
}

PROBLEMS = [
    {
        'title': 'Login endpoint returns 500 on wrong password',
        'description': 'The login view crashes instead of returning 401 when the password is wrong. Fix it so bad credentials get a clean 401 and incomplete requests get a 400.',
        'difficulty': 'easy', 'field': 'backend', 'language': 'python', 'framework': 'django rest framework',
        'files': LOGIN_FILES,
        'hidden': LOGIN_HIDDEN,
    },
    {
        'title': 'Add soft delete to the notes model',
        'description': 'Deleting a note should hide it instead of removing the row. Deleted notes must not show up in the list endpoint, and a new trash endpoint lists them.',
        'difficulty': 'medium', 'field': 'backend', 'language': 'python', 'framework': 'django',
        'files': NOTES_FILES,
        'hidden': NOTES_HIDDEN,
    },
    {
        'title': 'Race condition in inventory reservation',
        'description': 'Two concurrent orders can reserve the same last item. Make reservation safe under concurrency without locking the whole table, and reject quantities below 1.',
        'difficulty': 'hard', 'field': 'backend', 'language': 'python', 'framework': 'django rest framework',
        'files': INVENTORY_FILES,
        'hidden': INVENTORY_HIDDEN,
    },
    {
        'title': 'Todo list re-renders on every keystroke',
        'description': 'Typing in the search box re-renders every todo item. Stop the extra renders without changing what the list shows.',
        'difficulty': 'medium', 'field': 'frontend', 'language': 'javascript', 'framework': 'react',
        'time_required': 120,
        'files': TODO_FILES,
        'hidden': TODO_HIDDEN,
    },
    {
        'title': 'Form submits twice on double click',
        'description': 'Users can double click Save and create two records. Disable the button while the request is in flight.',
        'difficulty': 'easy', 'field': 'frontend', 'language': 'typescript', 'framework': 'react',
        'time_required': 120,
        'files': PROFILE_FILES,
        'hidden': PROFILE_HIDDEN,
    },
    {
        'title': 'Product page is not statically generated',
        'description': 'The product page is rendered on every request. Prerender the known products at build time and revalidate them every 60 seconds.',
        'difficulty': 'hard', 'field': 'frontend', 'language': 'typescript', 'framework': 'next.js',
        'time_required': 240,
        'files': PRODUCT_PAGE_FILES,
        'hidden': PRODUCT_PAGE_HIDDEN,
    },
    {
        'title': 'Dockerfile runs the app as root',
        'description': 'The production image runs as root and ships build tools. Use a non-root user and a multi-stage build with a small final image.',
        'difficulty': 'easy', 'field': 'devops', 'language': 'python', 'framework': 'django',
        'files': {
            'README.md': (
                '# API image\n'
                '\n'
                'Security flagged our image: it runs as root and ships compilers.\n'
                '\n'
                'Use a multi-stage build. The final stage must use a small base image (slim, alpine or distroless),\n'
                'run as a non-root user, and still start the app with gunicorn.\n'
            ),
            'requirements.txt': 'Django>=6.1\ngunicorn>=23.0\npsycopg[binary]>=3.2\n',
            'Dockerfile': (
                'FROM python:3.12\n'
                'WORKDIR /app\n'
                'COPY . .\n'
                'RUN pip install -r requirements.txt\n'
                'CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000"]\n'
            ),
        },
        'hidden': DOCKERFILE_HIDDEN,
    },
    {
        'title': 'CI pipeline never caches dependencies',
        'description': 'Every CI run reinstalls all packages and takes 6 minutes. Add dependency caching keyed on the lock file.',
        'difficulty': 'medium', 'field': 'devops', 'language': 'javascript', 'framework': 'next.js',
        'files': {
            'README.md': (
                '# CI\n'
                '\n'
                'Every run reinstalls all packages from scratch.\n'
                '\n'
                'Cache npm dependencies keyed on `package-lock.json`, install exactly what the lock file says,\n'
                'and keep running the tests.\n'
            ),
            'package.json': (
                '{\n'
                '  "name": "shop",\n'
                '  "private": true,\n'
                '  "scripts": {"build": "next build", "test": "node --test"}\n'
                '}\n'
            ),
            '.github/workflows/ci.yml': (
                'name: CI\n'
                'on: [push]\n'
                'jobs:\n'
                '  test:\n'
                '    runs-on: ubuntu-latest\n'
                '    steps:\n'
                '      - uses: actions/checkout@v4\n'
                '      - uses: actions/setup-node@v4\n'
                '        with:\n'
                '          node-version: 24\n'
                '      - run: npm install\n'
                '      - run: npm test\n'
            ),
        },
        'hidden': CI_HIDDEN,
    },
    {
        'title': 'Compose stack starts the app before the database',
        'description': 'The app container crashes on boot because Postgres is not ready yet. Add a healthcheck and wait on it.',
        'difficulty': 'medium', 'field': 'devops', 'language': 'python', 'framework': 'django',
        'files': {
            'README.md': (
                '# Stack\n'
                '\n'
                'On a cold start the app crashes because Postgres is not accepting connections yet.\n'
                '\n'
                'Give `db` a healthcheck based on `pg_isready` and make `app` wait until `db` is healthy.\n'
                'The app must stay published on port 8000.\n'
            ),
            'Dockerfile': (
                'FROM python:3.12-slim\n'
                'WORKDIR /app\n'
                'COPY . .\n'
                'RUN pip install -r requirements.txt\n'
                'CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000"]\n'
            ),
            'docker-compose.yml': (
                'services:\n'
                '  db:\n'
                '    image: postgres:16\n'
                '    environment:\n'
                '      POSTGRES_DB: app\n'
                '      POSTGRES_USER: app\n'
                '      POSTGRES_PASSWORD: app\n'
                '  app:\n'
                '    build: .\n'
                '    depends_on:\n'
                '      - db\n'
                '    environment:\n'
                '      DATABASE_URL: postgres://app:app@db:5432/app\n'
                '    ports:\n'
                '      - "8000:8000"\n'
            ),
        },
        'hidden': COMPOSE_HIDDEN,
    },
]

COMMENTS = [
    'Took me a while to find the root cause, nice one.',
    'Is the README hint enough? I got stuck for an hour.',
    'Hidden tests are strict about edge cases, read the description carefully.',
    'This is exactly the bug we had in production last month.',
    'Solved it, but my first attempt broke another endpoint.',
    'Good practice for interviews.',
    'Would love a follow-up problem on this topic.',
    'The difficulty label feels right.',
]

UPDATE_TITLES = [
    'Fix typo in the task description',
    'Clarify the expected response format',
    'Add a missing edge case to the README',
    'Mention the required Python version',
]


class Command(BaseCommand):
    help = 'Fill the database with dummy users, social accounts, problems, update requests, comments, likes and submissions. Safe to run more than once.'

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Refusing to seed: DEBUG is off.')
        password = os.getenv('SEED_PASSWORD')
        if not password:
            raise CommandError('Set SEED_PASSWORD to the password the seed users should get.')

        rng = random.Random(42)
        with transaction.atomic():
            users = self.seed_users(rng, password)
            self.seed_social_accounts(users)
            problems = self.seed_problems(users)
            self.seed_updates(rng, problems)
            self.seed_comments(rng, users, problems)
            self.seed_submissions(rng, users, Problem.objects.filter(status='accepted'))

        self.stdout.write(self.style.SUCCESS(
            f'Done. users={User.objects.count()} problems={Problem.objects.count()} '
            f'files={ProblemFile.objects.count()} comments={Comment.objects.count()} '
            f'likes={Like.objects.count()} submissions={Submission.objects.count()} '
            f'updates={UpdateProblem.objects.count()} social_accounts={SocialAccount.objects.count()}'
        ))

    def seed_users(self, rng, password):
        users = []
        for name in USERNAMES:
            user = User.objects.filter(username=name).first()
            if user is None:
                user = User.objects.create_user(username=name, email=f'{name}@example.com', password=password)
                UserLocation.objects.create(user=user, timezone=rng.choice(TIMEZONES))
            users.append(user)
        return users

    def seed_social_accounts(self, users):
        for i, user in enumerate(users[::2]):
            SocialAccount.objects.get_or_create(
                provider=SocialAccount.GOOGLE if i % 2 == 0 else SocialAccount.GITHUB,
                provider_user_id=f'seed-{user.username}',
                defaults={'user': user},
            )

    def seed_problems(self, users):
        problems = []
        for i, spec in enumerate(PROBLEMS):
            data = {k: v for k, v in spec.items() if k not in ('files', 'hidden', 'time_required')}
            data['time_required'] = spec.get('time_required', TIME_REQUIRED[spec['difficulty']])
            problem = Problem.objects.filter(title=data['title']).first()
            if problem is None:
                status = 'pending' if i == len(PROBLEMS) - 1 else 'accepted'
                problem = Problem.objects.create(**data, status=status, created_by=users[i % len(users)])
            else:
                Problem.objects.filter(pk=problem.pk).update(**data)
                problem.files.all().delete()
            ProblemFile.objects.bulk_create(
                [ProblemFile(problem=problem, directory=d, content=c) for d, c in spec['files'].items()]
                + [ProblemFile(problem=problem, directory=d, content=c, is_hidden=True) for d, c in spec['hidden'].items()]
            )
            problems.append(problem)
        return problems

    def seed_updates(self, rng, problems):
        for problem in problems:
            readme = problem.files.get(directory='README.md')
            for _ in range(rng.randint(0, 2)):
                title = rng.choice(UPDATE_TITLES)
                UpdateProblem.objects.create(
                    title=title,
                    problem=problem,
                    problem_file=readme,
                    new_content=f'{readme.content}\n{title}.\n',
                    status=rng.choice(['pending', 'accepted', 'rejected']),
                )

    def seed_comments(self, rng, users, problems):
        for problem in problems:
            if problem.comments.filter(user__in=users).exists():
                continue
            for author in rng.sample(users, rng.randint(1, 4)):
                comment = Comment.objects.create(user=author, problem=problem, text=rng.choice(COMMENTS))
                likers = rng.sample([u for u in users if u != author], rng.randint(0, 5))
                Like.objects.bulk_create([Like(user=u, comment=comment) for u in likers])
                comment.like_count = len(likers)
                comment.save(update_fields=['like_count'])

    def seed_submissions(self, rng, users, problems):
        problems = list(problems)
        now = timezone.now()
        for user in users:
            if user.submissions.exists():
                continue
            for _ in range(rng.randint(5, 30)):
                status = rng.choices(['done', 'failed', 'pending'], weights=[80, 15, 5])[0]
                submission = Submission.objects.create(
                    user=user,
                    problem=rng.choice(problems),
                    status=status,
                    score=rng.choice([0, 25, 50, 75, 100]) if status == 'done' else 0,
                    error_message='Container timed out' if status == 'failed' else None,
                )
                created_at = now - timedelta(days=rng.randint(0, 364), hours=rng.randint(0, 23))
                Submission.objects.filter(pk=submission.pk).update(created_at=created_at)
