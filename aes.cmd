@echo off
rem Run the AI Edit Stack CLI from any folder:  E:\AI-Edit_stack\aes.cmd <command> ...
rem Model downloads and the uv cache live on E: (C: is nearly full).
if not defined HF_HOME set "HF_HOME=E:\hf-models"
if not defined UV_CACHE_DIR set "UV_CACHE_DIR=E:\uv-cache"
if not defined TORCH_HOME set "TORCH_HOME=E:\hf-models\torch"
set "PYTHONIOENCODING=utf-8"
uv run --project "%~dp0." --extra gpu --extra ml aes %*
