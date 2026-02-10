#!/bin/bash
# Test script for Arboric API endpoints
# Make sure the API server is running first: arboric api

BASE_URL="http://localhost:8000"

echo "🧪 Testing Arboric API Endpoints"
echo "================================"
echo ""

# Test 1: Health Check
echo "1️⃣  Health Check"
curl -s "${BASE_URL}/api/v1/health" | python -m json.tool
echo ""
echo ""

# Test 2: System Status
echo "2️⃣  System Status"
curl -s "${BASE_URL}/api/v1/status" | python -m json.tool
echo ""
echo ""

# Test 3: Get Configuration
echo "3️⃣  Get Configuration"
curl -s "${BASE_URL}/api/v1/config" | python -m json.tool
echo ""
echo ""

# Test 4: Get Forecast
echo "4️⃣  Grid Forecast (US-WEST, 24h)"
curl -s "${BASE_URL}/api/v1/forecast?region=US-WEST&hours=24" | python -m json.tool | head -50
echo "... (truncated)"
echo ""
echo ""

# Test 5: Optimize Single Workload
echo "5️⃣  Optimize Single Workload"
curl -s -X POST "${BASE_URL}/api/v1/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "workload": {
      "name": "LLM Training",
      "duration_hours": 8,
      "power_draw_kw": 120,
      "deadline_hours": 24,
      "workload_type": "ml_training"
    },
    "region": "US-WEST"
  }' | python -m json.tool
echo ""
echo ""

# Test 6: Optimize Fleet
echo "6️⃣  Optimize Fleet (2 workloads)"
curl -s -X POST "${BASE_URL}/api/v1/fleet/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "workloads": [
      {
        "name": "ETL Pipeline",
        "duration_hours": 2,
        "power_draw_kw": 40,
        "deadline_hours": 12
      },
      {
        "name": "Model Training",
        "duration_hours": 6,
        "power_draw_kw": 80,
        "deadline_hours": 24
      }
    ],
    "region": "US-WEST"
  }' | python -m json.tool
echo ""
echo ""

# Test 7: Validation Error (Invalid workload)
echo "7️⃣  Validation Error Test (deadline < duration)"
curl -s -X POST "${BASE_URL}/api/v1/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "workload": {
      "name": "Bad Job",
      "duration_hours": 12,
      "power_draw_kw": 50,
      "deadline_hours": 4
    }
  }' | python -m json.tool
echo ""
echo ""

echo "✅ Testing complete!"
echo ""
echo "For interactive testing, visit:"
echo "  Swagger UI: ${BASE_URL}/docs"
echo "  ReDoc: ${BASE_URL}/redoc"
