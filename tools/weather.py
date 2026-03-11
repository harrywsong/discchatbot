from __future__ import annotations

import logging

import aiohttp

logger = logging.getLogger(__name__)


async def get_weather(location: str) -> str:
    """Get current weather and today's forecast for a location using wttr.in."""
    try:
        url = f"https://wttr.in/{location}?format=j1"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return f"Could not get weather for '{location}' (HTTP {resp.status})."
                data = await resp.json(content_type=None)

        current = data["current_condition"][0]
        area = data["nearest_area"][0]
        city = area["areaName"][0]["value"]
        country = area["country"][0]["value"]

        temp_c = current["temp_C"]
        temp_f = current["temp_F"]
        feels_c = current["FeelsLikeC"]
        feels_f = current["FeelsLikeF"]
        desc = current["weatherDesc"][0]["value"]
        humidity = current["humidity"]
        wind_kmph = current["windspeedKmph"]
        wind_dir = current["winddir16Point"]
        visibility = current["visibility"]

        today = data["weather"][0]
        max_c = today["maxtempC"]
        min_c = today["mintempC"]
        max_f = today["maxtempF"]
        min_f = today["mintempF"]

        return (
            f"**Weather in {city}, {country}**\n"
            f"Condition: {desc}\n"
            f"Temperature: {temp_c}°C / {temp_f}°F (feels like {feels_c}°C / {feels_f}°F)\n"
            f"Today: High {max_c}°C/{max_f}°F, Low {min_c}°C/{min_f}°F\n"
            f"Humidity: {humidity}% | Wind: {wind_kmph} km/h {wind_dir} | Visibility: {visibility} km"
        )
    except Exception as e:
        logger.warning("Weather fetch failed for '%s': %s", location, e)
        return f"Could not get weather for '{location}': {e}"


def make_weather_tool() -> dict:
    return {"name": "get_weather", "fn": get_weather}
