# Plan: V201 Commercial Activation & Viral Loop

## Objective
Finalize the commercial readiness of Alpha Hub Pro by activating monetization placeholders, adding a viral achievement system, and improving the macro "weather" reporting.

## Features
1. **AdMob/AdSense Activation**:
   - Inject the auto-ad script using the `publisher_id` from `config.json`.
   - Add a responsive ad container at the bottom of the Home tab (hidden for Pro users).
2. **Pro Trial Countdown & Conversion**:
   - If not Pro, show a "24h Free Trial" button.
   - If in Trial, show a persistent countdown bar at the top.
3. **Market "Weather" Summary**:
   - A single-line headline at the top of the Home screen (e.g., "Market Weather: Clear Skies - 85% Opportunity Breadth").
4. **Viral Achievement System**:
   - Locally tracked badges:
     - **Diamond Hands**: Hold an asset through a 10% dip (calculated locally).
     - **Alpha Hunter**: Buy when AHR < 0.45.
     - **Whale**: Total value > $10,000.
   - Display these on the "Vault" tab.
5. **Enhanced 'Professional Research' Poster**:
   - A new layout for the share card that looks like a Forbes/Bloomberg cover.

## Implementation Steps
1. Modify `haowu999_summary.py` to:
   - Calculate "Market Weather" based on `market_breadth` and `avg_ahr`.
   - Include the AdMob script tag in the HTML template.
   - Add the achievement badge logic in the frontend JavaScript.
   - Update the `index.html` generation logic.
2. Run the script and push to GitHub.
