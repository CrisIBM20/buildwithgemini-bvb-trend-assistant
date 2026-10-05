"""Firestore, GCS, and Gemini AI tools for BVB Trend Assistant equities & ETFs database."""

import asyncio
import datetime
import json
import urllib.request
from google import genai
from google.adk.tools import ToolContext
from google.cloud import firestore, storage
from google.genai import types

# Hardcode project ID and bucket name to avoid project number resolution issues on Agent Platform
FIRESTORE_PROJECT_ID = "qwiklabs-gcp-01-e13c31e58e65"
GCS_BUCKET_NAME = "bvb-trend-assistant-assets-qwiklabs-gcp-01-e13c31e58e65"
COLLECTION_NAME = "bvb_stocks"


def _get_firestore_client():
    return firestore.Client(project=FIRESTORE_PROJECT_ID)


def get_stock_info(ticker: str) -> dict:
    """Retrieve detailed information and current technical/fundamental data for a Romanian stock or ETF (BVB).

    Args:
        ticker: The asset ticker symbol (e.g., 'TLV', 'SNP', 'H2O', 'TVBETETF', 'ETFBETNG', 'BRD', 'DIGI', 'TGN', 'TEL', 'M', 'AQ', 'ONE', 'TTS', 'WINE', 'EL', 'ATB', 'EVER', 'TRANSI', 'INFINITY', 'LION', 'LONG', 'COTE', 'FP', 'BVB', 'ALU', 'TRP', 'SFG').

    Returns:
        A dictionary containing asset metrics, company/fund name, sector, asset_type ('Stock' or 'ETF'), price in RON, P/E ratio, dividend yield, and trend signal.
    """
    db = _get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(ticker.upper())
    doc = doc_ref.get()

    if not doc.exists:
        return {"error": f"Asset ticker '{ticker}' not found in BVB database."}

    return doc.to_dict()


def list_bvb_stocks(sector: str = None, asset_type: str = None) -> list[dict]:
    """List Romanian stocks and ETFs listed on the Bucharest Stock Exchange (BVB), optionally filtering by sector or asset_type.

    Args:
        sector: Optional sector filter (e.g., 'Banking', 'Energy', 'Utilities', 'Telecommunications', 'Healthcare', 'Real Estate', 'Transportation', 'Consumer Staples', 'Pharmaceuticals', 'Financial Services', 'Index ETF', 'Energy ETF').
        asset_type: Optional filter for asset type ('Stock' or 'ETF').

    Returns:
        A list of stock and ETF summaries from Firestore.
    """
    db = _get_firestore_client()
    query = db.collection(COLLECTION_NAME)

    if sector:
        query = query.where("sector", "==", sector)
    if asset_type:
        query = query.where("asset_type", "==", asset_type)

    docs = query.stream()
    assets = [doc.to_dict() for doc in docs]
    return assets


def update_stock_trend(
    ticker: str, trend_signal: str, price_ron: float = None, rsi_14: float = None
) -> dict:
    """Update or adjust the trend signal, current price, and RSI for a Romanian stock or ETF in the database.

    Args:
        ticker: Asset ticker symbol (e.g., 'TLV', 'SNP', 'TVBETETF').
        trend_signal: Trend classification ('BULLISH', 'BEARISH', or 'NEUTRAL').
        price_ron: Optional updated price in RON.
        rsi_14: Optional updated 14-period Relative Strength Index value.

    Returns:
        A dictionary status confirming the update.
    """
    db = _get_firestore_client()
    doc_ref = db.collection(COLLECTION_NAME).document(ticker.upper())
    doc = doc_ref.get()

    if not doc.exists:
        return {"error": f"Asset '{ticker}' not found to update."}

    update_data = {
        "trend_signal": trend_signal.upper(),
        "last_updated": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    if price_ron is not None:
        update_data["price_ron"] = price_ron
    if rsi_14 is not None:
        update_data["rsi_14"] = rsi_14

    doc_ref.update(update_data)
    return {
        "status": "success",
        "ticker": ticker.upper(),
        "updated_fields": update_data,
    }


def calculate_technical_indicators(ticker: str) -> dict:
    """Calculate RSI momentum and technical trend rating for a Romanian stock or ETF (BVB), updating Firestore.

    Args:
        ticker: Asset ticker symbol (e.g., 'TLV', 'SNP', 'H2O', 'TVBETETF').

    Returns:
        A dictionary with RSI momentum evaluation, dividend appeal score, composite technical rating, and database update status.
    """
    stock = get_stock_info(ticker)
    if "error" in stock:
        return stock

    rsi = stock.get("rsi_14", 50.0)
    pe = stock.get("pe_ratio", 10.0)
    div_yield = stock.get("dividend_yield_pct", 0.0)

    # Momentum assessment
    if rsi >= 70:
        momentum = "OVERBOUGHT"
        rating = "BEARISH_REVERSAL_RISK"
    elif rsi <= 30:
        momentum = "OVERSOLD"
        rating = "STRONG_BUY_OPPORTUNITY"
    elif rsi > 55:
        momentum = "BULLISH_MOMENTUM"
        rating = "BULLISH"
    else:
        momentum = "NEUTRAL"
        rating = "NEUTRAL"

    # Dividend & Valuation signal
    value_signal = "NEUTRAL"
    if div_yield >= 8.0 and pe < 10.0:
        value_signal = "HIGH_DIVIDEND_UNDERVALUED"

    update_stock_trend(ticker, rating, rsi_14=rsi)

    return {
        "ticker": ticker.upper(),
        "company_name": stock.get("company_name"),
        "rsi_14": rsi,
        "momentum_status": momentum,
        "valuation_signal": value_signal,
        "calculated_rating": rating,
        "price_ron": stock.get("price_ron"),
    }


def get_ron_exchange_rates(
    base_currency: str = "RON", target_currencies: str = "EUR,USD,GBP"
) -> dict:
    """Fetch official live European Central Bank (ECB) exchange rates for Romanian Leu (RON) or major currencies via Frankfurter API.

    Args:
        base_currency: The base currency symbol (default: 'RON', 'EUR', or 'USD').
        target_currencies: Comma-separated list of target currency symbols (e.g., 'EUR,USD,GBP').

    Returns:
        A dictionary with live conversion rates, base currency, and latest date from European Central Bank.
    """
    url = f"https://api.frankfurter.app/latest?from={base_currency.upper()}&to={target_currencies.upper()}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "BVB-Trend-Assistant/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return {
                "base": data.get("base"),
                "date": data.get("date"),
                "rates": data.get("rates"),
            }
    except Exception as e:
        return {"error": f"Failed to fetch exchange rates: {str(e)}"}


async def generate_stock_trend_image(
    ticker: str, tool_context: ToolContext
) -> dict:
    """Generate a visual stock trend infographic image for a BVB asset using gemini-3.1-flash-lite-image in the global region, save as artifact, and upload to public GCS.

    Args:
        ticker: Asset ticker symbol (e.g., 'TLV', 'SNP', 'H2O', 'TVBETETF').
        tool_context: ADK ToolContext for artifact saving in Playground.

    Returns:
        A dictionary containing the public HTTPS URL of the uploaded image and artifact details.
    """
    # 1. Generate image using gemini-3.1-flash-lite-image in location='global'
    client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT_ID,
        location="global",
    )
    prompt = (
        f"A sleek financial stock chart infographic badge for Bucharest Stock Exchange company {ticker.upper()} "
        "showing bullish trend indicators, financial stock metrics, modern design"
    )
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
    )

    image_bytes = response.candidates[0].content.parts[0].inline_data.data
    filename = f"{ticker.lower()}_trend_badge.png"

    # 2. Save image as Playground artifact using tool_context.save_artifact
    artifact_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")
    await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 3. Upload same image bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(image_bytes, content_type="image/png")

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

    return {
        "status": "success",
        "ticker": ticker.upper(),
        "public_url": public_url,
        "filename": filename,
    }


async def generate_stock_trend_video(
    ticker: str, tool_context: ToolContext
) -> dict:
    """Generate a short video summary for a BVB stock or ETF using Google's Omni model (gemini-omni-flash-preview) in the global region, save as artifact, and upload to public GCS.

    Args:
        ticker: Asset ticker symbol (e.g., 'TLV', 'SNP', 'H2O', 'TVBETETF').
        tool_context: ADK ToolContext for artifact saving in Playground.

    Returns:
        A dictionary containing the public HTTPS URL of the uploaded video and artifact details.
    """
    client = genai.Client(
        vertexai=True,
        project=FIRESTORE_PROJECT_ID,
        location="global",
    )
    prompt = (
        f"A short video animation showing market trends, chart dynamics, and stock movement for Bucharest Stock Exchange ticker {ticker.upper()}."
    )

    interaction = client.interactions.create(
        model="gemini-omni-flash-preview",
        input=prompt,
        background=True,
    )

    # Poll interaction status until complete
    while True:
        curr = client.interactions.get(id=interaction.id)
        if curr.status not in ["in_progress", "pending", "queued"]:
            break
        await asyncio.sleep(2)

    if curr.status != "completed" and hasattr(curr, "error") and curr.error:
        return {"error": f"Video generation failed: {curr.error}"}

    # Extract video bytes from output_video
    video_bytes = None
    if hasattr(curr, "output_video") and curr.output_video:
        if hasattr(curr.output_video, "data") and curr.output_video.data:
            video_bytes = curr.output_video.data
        elif hasattr(curr.output_video, "inline_data") and curr.output_video.inline_data:
            video_bytes = curr.output_video.inline_data.data

    if not video_bytes:
        return {
            "error": f"Video generation finished with status '{curr.status}', but no video bytes were returned."
        }

    filename = f"{ticker.lower()}_trend_video.mp4"

    # 1. Save video as Playground artifact using tool_context.save_artifact
    artifact_part = types.Part.from_bytes(data=video_bytes, mime_type="video/mp4")
    await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload same video bytes to public Cloud Storage bucket
    storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
    bucket = storage_client.bucket(GCS_BUCKET_NAME)
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type="video/mp4")

    public_url = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/{filename}"

    return {
        "status": "success",
        "ticker": ticker.upper(),
        "public_url": public_url,
        "filename": filename,
    }

