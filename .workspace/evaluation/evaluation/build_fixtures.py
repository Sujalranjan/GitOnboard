"""
Builds the 15 canonical benchmark repository fixtures with 50 curated ground-truth facts.
"""
from __future__ import annotations
import json
from pathlib import Path


FIXTURES = [
    {
        "repo_id": "01_minimal_python_cli",
        "description": "Minimal Python CLI tool with pyproject.toml and click",
        "files": {
            "pyproject.toml": "[project]\nname = 'mincli'\nversion = '0.1.0'\ndependencies = ['click>=8.0.0']\n",
            "src/mincli/main.py": "import click\n\n@click.command()\ndef main():\n    click.echo('Hello MinCLI')\n",
            "README.md": "# MinCLI\nA minimal command line interface tool written in Python.\nUses click for argument parsing.\n",
        },
        "ground_truth": {
            "languages": ["Python"],
            "frameworks": ["click"],
            "databases": [],
            "deployable_units": ["cli"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Written in Python",
                "Uses click CLI framework",
                "Entrypoint is src/mincli/main.py"
            ]
        }
    },
    {
        "repo_id": "02_fastapi_backend",
        "description": "FastAPI HTTP API with PostgreSQL and SQLAlchemy",
        "files": {
            "requirements.txt": "fastapi==0.110.0\nuvicorn==0.28.0\npsycopg2-binary==2.9.9\nsqlalchemy==2.0.28\n",
            "app/main.py": "from fastapi import FastAPI\nfrom app.db import Base, engine\napp = FastAPI(title='UserAPI')\n",
            "app/db.py": "from sqlalchemy import create_engine\nfrom sqlalchemy.orm import declarative_base\nengine = create_engine('postgresql://user:pass@localhost:5432/appdb')\nBase = declarative_base()\n",
            "app/routes/users.py": "from fastapi import APIRouter\nrouter = APIRouter(prefix='/api/v1/users')\n",
            "README.md": "# User API Service\nFastAPI REST service backed by PostgreSQL database.\n",
        },
        "ground_truth": {
            "languages": ["Python"],
            "frameworks": ["FastAPI", "SQLAlchemy", "Uvicorn"],
            "databases": ["PostgreSQL"],
            "deployable_units": ["backend_api"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Uses FastAPI web framework",
                "Uses PostgreSQL database with SQLAlchemy",
                "Exposes /api/v1/users route",
                "Database connection configured in app/db.py"
            ]
        }
    },
    {
        "repo_id": "03_flask_monolith",
        "description": "Flask monolith with SQLite and Jinja templates",
        "files": {
            "requirements.txt": "Flask==3.0.2\nFlask-SQLAlchemy==3.1.1\n",
            "app.py": "from flask import Flask, render_template\napp = Flask(__name__)\napp.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'\n",
            "templates/index.html": "<html><body><h1>Flask App</h1></body></html>\n",
            "README.md": "# Flask Monolith\nTraditional server-rendered Flask web application with SQLite database.\n",
        },
        "ground_truth": {
            "languages": ["Python", "HTML"],
            "frameworks": ["Flask", "Flask-SQLAlchemy"],
            "databases": ["SQLite"],
            "deployable_units": ["web_monolith"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Built with Flask framework",
                "Uses SQLite as local database",
                "Renders HTML templates with Jinja"
            ]
        }
    },
    {
        "repo_id": "04_express_api",
        "description": "Express.js REST API with MongoDB and Mongoose",
        "files": {
            "package.json": '{\n  "name": "express-api",\n  "version": "1.0.0",\n  "dependencies": {\n    "express": "^4.18.2",\n    "mongoose": "^8.2.1",\n    "cors": "^2.8.5"\n  }\n}\n',
            "src/server.js": "const express = require('express');\nconst mongoose = require('mongoose');\nconst app = express();\nmongoose.connect('mongodb://localhost:27017/shop');\n",
            "src/routes/items.js": "const express = require('express');\nconst router = express.Router();\nmodule.exports = router;\n",
            "README.md": "# Shop API\nNode.js and Express REST API connected to MongoDB database.\n",
        },
        "ground_truth": {
            "languages": ["JavaScript"],
            "frameworks": ["Express", "Mongoose"],
            "databases": ["MongoDB"],
            "deployable_units": ["backend_api"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Written in JavaScript on Node.js",
                "Uses Express framework",
                "Uses MongoDB with Mongoose ODM"
            ]
        }
    },
    {
        "repo_id": "05_django_rest",
        "description": "Django REST Framework with documentation contradiction (claims SQLite but uses Postgres)",
        "files": {
            "requirements.txt": "django==5.0.3\ndjangorestframework==3.14.0\npsycopg2-binary==2.9.9\n",
            "myproject/settings.py": "DATABASES = {'default': {'ENGINE': 'django.db.backends.postgresql', 'NAME': 'prod_db'}}\n",
            "myproject/urls.py": "from django.urls import path\nurlpatterns = []\n",
            "README.md": "# Django Portal\nBuilt on Django REST Framework.\nNote: Uses SQLite database for storage.\n",
        },
        "ground_truth": {
            "languages": ["Python"],
            "frameworks": ["Django", "Django REST Framework"],
            "databases": ["PostgreSQL"],
            "deployable_units": ["web_backend"],
            "declared_unused": [],
            "known_contradictions": [
                {
                    "claimed": "SQLite",
                    "actual": "PostgreSQL"
                }
            ],
            "unverified_doc_claims": [],
            "important_facts": [
                "Uses Django framework",
                "Uses PostgreSQL in settings.py",
                "Documentation contradicts code by claiming SQLite"
            ]
        }
    },
    {
        "repo_id": "06_go_microservice",
        "description": "Go microservice with Gin and Redis cache",
        "files": {
            "go.mod": "module github.com/example/orders\n\ngo 1.22\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.1\n\tgithub.com/redis/go-redis/v9 v9.5.1\n)\n",
            "main.go": "package main\nimport (\n\t\"github.com/gin-gonic/gin\"\n\t\"github.com/redis/go-redis/v9\"\n)\nfunc main() {\n\tr := gin.Default()\n\tr.Run(\":8080\")\n}\n",
            "README.md": "# Order Microservice\nHigh performance Go microservice using Gin and Redis caching.\n",
        },
        "ground_truth": {
            "languages": ["Go"],
            "frameworks": ["Gin"],
            "databases": ["Redis"],
            "deployable_units": ["microservice"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Written in Go",
                "Uses Gin HTTP web framework",
                "Uses Redis for caching",
                "Runs on port 8080"
            ]
        }
    },
    {
        "repo_id": "07_nextjs_frontend",
        "description": "Next.js 14 App Router with React and Tailwind CSS",
        "files": {
            "package.json": '{\n  "name": "portal-ui",\n  "dependencies": {\n    "next": "^14.1.0",\n    "react": "^18.2.0",\n    "tailwindcss": "^3.4.1"\n  }\n}\n',
            "app/page.tsx": "export default function Home() { return <main><h1>Portal UI</h1></main>; }\n",
            "app/layout.tsx": "export default function RootLayout({ children }: { children: React.ReactNode }) { return <html><body>{children}</body></html>; }\n",
            "README.md": "# Portal UI\nModern web frontend built with Next.js 14 App Router and Tailwind CSS.\n",
        },
        "ground_truth": {
            "languages": ["TypeScript"],
            "frameworks": ["Next.js", "React", "Tailwind CSS"],
            "databases": [],
            "deployable_units": ["frontend_spa"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Written in TypeScript",
                "Uses Next.js App Router",
                "Uses Tailwind CSS for styling"
            ]
        }
    },
    {
        "repo_id": "08_rust_cli_utility",
        "description": "Rust command line tool using Tokio and Clap",
        "files": {
            "Cargo.toml": "[package]\nname = 'rust-parser'\nversion = '0.1.0'\nedition = '2021'\n\n[dependencies]\nclap = { version = '4.4', features = ['derive'] }\ntokio = { version = '1.35', features = ['full'] }\n",
            "src/main.rs": "use clap::Parser;\n#[derive(Parser)]\nstruct Cli {}\n#[tokio::main]\nasync fn main() {}\n",
            "README.md": "# Rust Parser\nAsync command line parser written in Rust using Tokio and Clap.\n",
        },
        "ground_truth": {
            "languages": ["Rust"],
            "frameworks": ["Tokio", "Clap"],
            "databases": [],
            "deployable_units": ["cli"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Written in Rust edition 2021",
                "Uses Tokio async runtime",
                "Uses Clap for command line argument parsing"
            ]
        }
    },
    {
        "repo_id": "09_java_spring_boot",
        "description": "Java Spring Boot microservice with Maven and MySQL",
        "files": {
            "pom.xml": '<project>\n  <modelVersion>4.0.0</modelVersion>\n  <groupId>com.example</groupId>\n  <artifactId>account-service</artifactId>\n  <dependencies>\n    <dependency>\n      <groupId>org.springframework.boot</groupId>\n      <artifactId>spring-boot-starter-web</artifactId>\n    </dependency>\n    <dependency>\n      <groupId>mysql</groupId>\n      <artifactId>mysql-connector-java</artifactId>\n    </dependency>\n  </dependencies>\n</project>\n',
            "src/main/java/com/example/Application.java": "package com.example;\nimport org.springframework.boot.SpringApplication;\nimport org.springframework.boot.autoconfigure.SpringBootApplication;\n@SpringBootApplication\npublic class Application {\n  public static void main(String[] args) {\n    SpringApplication.run(Application.class, args);\n  }\n}\n",
            "README.md": "# Account Service\nEnterprise account management service built with Spring Boot and MySQL.\n",
        },
        "ground_truth": {
            "languages": ["Java"],
            "frameworks": ["Spring Boot", "Maven"],
            "databases": ["MySQL"],
            "deployable_units": ["backend_service"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Built in Java with Spring Boot",
                "Uses Maven build configuration pom.xml",
                "Connects to MySQL database"
            ]
        }
    },
    {
        "repo_id": "10_python_data_pipeline",
        "description": "Data engineering pipeline with Pandas, PyArrow and Clickhouse client",
        "files": {
            "pyproject.toml": "[project]\nname = 'datapipeline'\ndependencies = ['pandas>=2.2.0', 'pyarrow>=15.0.0', 'clickhouse-driver>=0.2.7']\n",
            "pipeline/extract.py": "import pandas as pd\nimport pyarrow as pa\nfrom clickhouse_driver import Client\nclient = Client('localhost')\n",
            "README.md": "# ETL Data Pipeline\nBatch processing pipeline extracting and ingesting analytics data into Clickhouse.\n",
        },
        "ground_truth": {
            "languages": ["Python"],
            "frameworks": ["Pandas", "PyArrow"],
            "databases": ["ClickHouse"],
            "deployable_units": ["data_pipeline"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Python ETL pipeline",
                "Uses Pandas and PyArrow for tabular data manipulation",
                "Connects to ClickHouse database"
            ]
        }
    },
    {
        "repo_id": "11_ruby_rails_app",
        "description": "Ruby on Rails web application with PostgreSQL",
        "files": {
            "Gemfile": "source 'https://rubygems.org'\ngem 'rails', '~> 7.1.3'\ngem 'pg', '~> 1.5'\n",
            "config/application.rb": "require_relative 'boot'\nrequire 'rails/all'\n",
            "config/database.yml": "default: &default\n  adapter: postgresql\n  encoding: unicode\n",
            "README.md": "# Rails Commerce\nFull-stack e-commerce application built on Ruby on Rails 7 with PostgreSQL.\n",
        },
        "ground_truth": {
            "languages": ["Ruby"],
            "frameworks": ["Rails"],
            "databases": ["PostgreSQL"],
            "deployable_units": ["web_app"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Built with Ruby on Rails 7",
                "Uses PostgreSQL database configured in database.yml",
                "Managed with Bundler Gemfile"
            ]
        }
    },
    {
        "repo_id": "12_multiservice_monorepo",
        "description": "Monorepo containing FastAPI backend and React frontend with Docker Compose",
        "files": {
            "docker-compose.yml": "version: '3.8'\nservices:\n  api:\n    build: ./services/api\n    ports: ['8000:8000']\n  web:\n    build: ./services/web\n    ports: ['3000:3000']\n",
            "services/api/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "services/api/requirements.txt": "fastapi==0.110.0\nuvicorn==0.28.0\n",
            "services/web/package.json": '{\n  "name": "web",\n  "dependencies": { "react": "^18.2.0" }\n}\n',
            "README.md": "# Platform Monorepo\nMulti-service architecture with FastAPI backend under services/api and React frontend under services/web.\n",
        },
        "ground_truth": {
            "languages": ["Python", "JavaScript"],
            "frameworks": ["FastAPI", "React", "Docker Compose"],
            "databases": [],
            "deployable_units": ["services/api", "services/web"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Multi-service monorepo structure",
                "Backend service located at services/api using FastAPI",
                "Frontend service located at services/web using React",
                "Orchestrated with Docker Compose"
            ]
        }
    },
    {
        "repo_id": "13_legacy_php_portal",
        "description": "Legacy PHP web app with MySQL PDO connection",
        "files": {
            "composer.json": '{\n  "name": "legacy/portal",\n  "require": {\n    "php": ">=7.4",\n    "twig/twig": "^3.0"\n  }\n}\n',
            "index.php": "<?php\n$pdo = new PDO('mysql:host=localhost;dbname=portal', 'user', 'pass');\n",
            "README.md": "# Legacy Portal\nLegacy PHP application using Twig template engine and MySQL database.\n",
        },
        "ground_truth": {
            "languages": ["PHP"],
            "frameworks": ["Twig"],
            "databases": ["MySQL"],
            "deployable_units": ["web_portal"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Written in PHP >=7.4",
                "Uses Twig template engine",
                "Connects to MySQL database using PDO"
            ]
        }
    },
    {
        "repo_id": "14_serverless_functions",
        "description": "AWS Lambda Serverless project with Python handlers",
        "files": {
            "serverless.yml": "service: lambda-analytics\nprovider:\n  name: aws\n  runtime: python3.11\nfunctions:\n  processEvent:\n    handler: handler.process\n",
            "handler.py": "import json\ndef process(event, context):\n    return {'statusCode': 200, 'body': json.dumps('processed')}\n",
            "README.md": "# Serverless Analytics\nServerless event processing functions deployed on AWS Lambda with Python 3.11.\n",
        },
        "ground_truth": {
            "languages": ["Python"],
            "frameworks": ["Serverless Framework", "AWS Lambda"],
            "databases": [],
            "deployable_units": ["serverless_function"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Serverless Framework project",
                "Targets AWS Lambda with python3.11 runtime",
                "Entrypoint handler in handler.py"
            ]
        }
    },
    {
        "repo_id": "15_fullstack_ai_agent",
        "description": "Fullstack AI agent service with FastAPI, ChromaDB, and LangChain",
        "files": {
            "pyproject.toml": "[project]\nname = 'ai-agent'\ndependencies = ['fastapi', 'chromadb', 'langchain-core', 'psycopg[binary]']\n",
            "agent/server.py": "from fastapi import FastAPI\nimport chromadb\napp = FastAPI(title='AgentAPI')\nclient = chromadb.Client()\n",
            "README.md": "# AI Agent Service\nFastAPI agent server integrating ChromaDB vector search and PostgreSQL relational storage.\n",
        },
        "ground_truth": {
            "languages": ["Python"],
            "frameworks": ["FastAPI", "LangChain", "ChromaDB"],
            "databases": ["ChromaDB", "PostgreSQL"],
            "deployable_units": ["ai_agent_service"],
            "declared_unused": [],
            "known_contradictions": [],
            "unverified_doc_claims": [],
            "important_facts": [
                "Fullstack AI agent service",
                "Uses FastAPI web framework",
                "Integrates ChromaDB for vector retrieval",
                "Uses PostgreSQL for relational persistence"
            ]
        }
    },
]


def write_fixtures():
    fixtures_dir = Path("evaluation/fixtures")
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    for item in FIXTURES:
        out_file = fixtures_dir / f"{item['repo_id']}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(item, f, indent=2)
    print(f"Successfully generated {len(FIXTURES)} benchmark fixtures in {fixtures_dir}")


if __name__ == "__main__":
    write_fixtures()
