import { NextRequest, NextResponse } from "next/server";
import { contractPath } from "@/lib/api-contract";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const response = await fetch(`${BACKEND_URL}${contractPath("trading.manual")}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ticker: body.symbol || body.ticker,
        side: (body.action || body.side || "buy").toLowerCase(),
        quantity: body.quantity,
        limit_price: body.limit_price || body.limitPrice,
        stop_loss: body.stop_loss || body.stopLoss,
        take_profit: body.take_profit || body.takeProfit,
        order_type: body.order_type || "market",
        time_in_force: body.time_in_force || "day",
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
