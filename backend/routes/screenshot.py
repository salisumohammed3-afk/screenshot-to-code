import base64
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import httpx
from urllib.parse import urlparse

router = APIRouter()


def normalize_url(url: str) -> str:
    """
    Normalize URL to ensure it has a proper protocol.
    If no protocol is specified, default to https://
    """
    url = url.strip()
    
    # Parse the URL
    parsed = urlparse(url)
    
    # Check if we have a scheme
    if not parsed.scheme:
        # No scheme, add https://
        url = f"https://{url}"
    elif parsed.scheme in ['http', 'https']:
        # Valid scheme, keep as is
        pass
    else:
        # Check if this might be a domain with port (like example.com:8080)
        # urlparse treats this as scheme:netloc, but we want to handle it as domain:port
        if ':' in url and not url.startswith(('http://', 'https://', 'ftp://', 'file://')):
            # Likely a domain:port without protocol
            url = f"https://{url}"
        else:
            # Invalid protocol
            raise ValueError(f"Unsupported protocol: {parsed.scheme}")
    
    return url


def bytes_to_data_url(image_bytes: bytes, mime_type: str) -> str:
    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime_type};base64,{base64_image}"


async def capture_screenshot_screenshotone(
    target_url: str, api_key: str, device: str = "desktop"
) -> bytes:
    api_base_url = "https://api.screenshotone.com/take"

    params = {
        "access_key": api_key,
        "url": target_url,
        "full_page": "true",
        "device_scale_factor": "1",
        "format": "png",
        "block_ads": "true",
        "block_cookie_banners": "true",
        "block_trackers": "true",
        "cache": "false",
        "viewport_width": "342",
        "viewport_height": "684",
    }

    if device == "desktop":
        params["viewport_width"] = "1280"
        params["viewport_height"] = "832"

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(api_base_url, params=params)
        if response.status_code == 200 and response.content:
            return response.content
        else:
            raise Exception("Error taking screenshot")


async def capture_screenshot_microlink(
    target_url: str, device: str = "desktop"
) -> bytes:
    """Free screenshot service via microlink.io — no API key required."""
    params = {
        "url": target_url,
        "screenshot": "true",
        "meta": "false",
        "embed": "screenshot.url",
    }

    if device == "mobile":
        params["viewport.width"] = "375"
        params["viewport.height"] = "812"
    else:
        params["viewport.width"] = "1280"
        params["viewport.height"] = "832"

    async with httpx.AsyncClient(timeout=60) as client:
        # First call: get the screenshot URL from the JSON response
        json_response = await client.get(
            "https://api.microlink.io/", params=params
        )
        if json_response.status_code != 200:
            raise Exception("Error taking screenshot via microlink.io")

        data = json_response.json()
        screenshot_url = (
            data.get("data", {}).get("screenshot", {}).get("url")
        )
        if not screenshot_url:
            raise Exception("No screenshot URL returned by microlink.io")

        # Second call: download the actual image bytes
        img_response = await client.get(screenshot_url)
        if img_response.status_code == 200 and img_response.content:
            return img_response.content
        else:
            raise Exception("Failed to download screenshot image")


async def capture_screenshot(
    target_url: str, api_key: str, device: str = "desktop"
) -> bytes:
    if api_key:
        return await capture_screenshot_screenshotone(target_url, api_key, device)
    else:
        return await capture_screenshot_microlink(target_url, device)


class ScreenshotRequest(BaseModel):
    url: str
    apiKey: Optional[str] = None


class ScreenshotResponse(BaseModel):
    url: str


@router.post("/api/screenshot")
async def app_screenshot(request: ScreenshotRequest):
    # Extract the URL from the request body
    url = request.url
    api_key = request.apiKey

    try:
        # Normalize the URL
        normalized_url = normalize_url(url)
        
        # Capture screenshot with normalized URL
        image_bytes = await capture_screenshot(normalized_url, api_key=api_key)

        # Convert the image bytes to a data url
        data_url = bytes_to_data_url(image_bytes, "image/png")

        return ScreenshotResponse(url=data_url)
    except ValueError as e:
        # Handle URL normalization errors
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        # Handle other errors
        raise HTTPException(status_code=500, detail=f"Error capturing screenshot: {str(e)}")
