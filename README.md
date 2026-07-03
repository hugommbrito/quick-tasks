# ⚡ Quick Tasks

Gerenciador de tarefas diárias com kanban board, subtasks e labels de prioridade. Roda localmente com acesso mobile via ngrok.

## Features

- **Kanban board** — colunas Todo / Doing / Done
- **Subtasks** — crie subtasks dentro de cada task, com progresso exibido no card
- **Labels** — 🔴 Urgente e ⭐ Importante (matriz de Eisenhower)
- **Drag-and-drop** — reordene e mova cards entre colunas
- **Persistência** — banco SQLite local, dados sobrevivem entre sessões
- **Mobile** — layout responsivo; acesso remoto via ngrok

## Requisitos

- Python 3.8+
- pip3

## Instalação e start

### Com venv (recomendado)

```bash
# Cria e ativa o ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instala as dependências
pip install -r requirements.txt

# Inicia o servidor
python main.py
```

Nas próximas vezes, apenas ative o venv antes de rodar:

```bash
source .venv/bin/activate
python main.py
```

### Sem venv

```bash
pip3 install -r requirements.txt
./start.sh
```

Acesse em [http://localhost:8000](http://localhost:8000).

O banco `tasks.db` é criado automaticamente na primeira execução.

## Acesso mobile (ngrok)

Com o servidor rodando, em outro terminal:

```bash
ngrok http 8000
```

Use a URL gerada (`https://xxxx.ngrok.io`) no celular.

## Atalhos de teclado

| Tecla | Ação |
|---|---|
| `N` | Nova task |
| `Cmd+Enter` / `Ctrl+Enter` | Salvar modal |
| `Esc` | Fechar modal |

## Stack

- **Backend** — FastAPI + SQLite (Python stdlib)
- **Frontend** — HTML/JS vanilla + Tailwind CSS + SortableJS (via CDN, sem build step)

## Dependências Python

| Pacote | Para que serve |
|---|---|
| `fastapi` | Framework web |
| `uvicorn[standard]` | Servidor ASGI |
| `python-multipart` | Parser de `multipart/form-data` (necessário para o FastAPI processar formulários) |
