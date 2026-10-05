# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from pathlib import Path

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.a2ui_utils import a2ui_callback
from app.tools import (
    calculate_technical_indicators,
    generate_stock_trend_image,
    generate_stock_trend_video,
    get_ron_exchange_rates,
    get_stock_info,
    list_bvb_stocks,
    update_stock_trend,
)


PROJECT_ID = "qwiklabs-gcp-01-e13c31e58e65"
LOCATION = "us-east1"
MEMORY_BANK_ID = "7354748726914580480"

DEPLOYMENT_METADATA_PATH = Path(__file__).parent.parent / "deployment_metadata.json"

code_executor = None
if DEPLOYMENT_METADATA_PATH.exists():
    try:
        with open(DEPLOYMENT_METADATA_PATH) as f:
            meta = json.load(f)
            agent_engine_id = meta.get("remote_agent_runtime_id")
            if agent_engine_id:
                code_executor = AgentEngineSandboxCodeExecutor(
                    agent_engine_resource_name=agent_engine_id
                )
    except Exception:
        pass

if code_executor is None:
    code_executor = AgentEngineSandboxCodeExecutor()


async def generate_memories_callback(callback_context: CallbackContext):
    """Callback triggered after each turn to extract and store durable facts into Memory Bank."""
    try:
        await callback_context.add_session_to_memory()
    except Exception as e:
        print(f"Memory bank callback note: {e}")
    return None



schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are BVB Trend Assistant, an expert AI advisor for equities and ETFs listed on the Bucharest Stock Exchange (BVB / BSE). "
        "You help investors analyze stock & ETF trends, calculate technical indicators (RSI momentum, ratings), fundamental metrics (P/E ratio, Dividend Yield), market performance, and live currency conversions (RON <-> EUR/USD). "
        "You remember the user's stated preferences, investment goals, portfolio holdings, and risk tolerance across conversations."
    ),
    workflow_description=(
        "Analyze the request and return structured UI cards or text when appropriate. "
        "You can execute Python code safely in a sandbox to compute financial modeling or statistical calculations. "
        "Use the provided tools to query stock/ETF metrics from Firestore, calculate technical indicator ratings, fetch ECB exchange rates for RON, generate trend badge images using Gemini Image Gen, list equities or ETFs by sector, and update trend signals."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=code_executor,
    tools=[
        get_stock_info,
        list_bvb_stocks,
        update_stock_trend,
        calculate_technical_indicators,
        get_ron_exchange_rates,
        generate_stock_trend_image,
        generate_stock_trend_video,
        PreloadMemoryTool(),
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)


app = App(
    root_agent=root_agent,
    name="app",
)
