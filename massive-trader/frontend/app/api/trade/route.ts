import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const response = await fetch(`${BACKEND_URL}/api/trade`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        symbol: body.symbol,
        action: body.action,
        quantity: body.quantity,
        entry_price: body.entry_price || body.entryPrice,
        stop_loss: body.stop_loss || body.stopLoss,
        take_profit: body.take_profit || body.takeProfit,
        order_type: body.order_type || "bracket",
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      return NextResponse.json(
        { error: `Trade execution failed: ${error}` },
        { status: response.status }
      );
    }

    const result = await response.json();
    return NextResponse.json(result);
  } catch (error) {
    console.error("Trade execution error:", error);
    return NextResponse.json(
      { error: "Trade execution failed" },
      { status: 500 }
    );
  }
}
