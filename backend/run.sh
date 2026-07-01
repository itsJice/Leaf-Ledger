#!/bin/bash

.venv/bin/python -m uvicorn main:app --reload --reload-dir app
