"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { Search, TrendingUp, TrendingDown, Star, Flame, Zap, Building2, Cpu, Heart, Fuel, ShoppingCart, Factory, Tv } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

// Ticker metadata for display - 200+ stocks
const TICKER_INFO: Record<string, { name: string; sector: string }> = {
  // ============ MEGA CAP TECH ============
  AAPL: { name: "Apple", sector: "Tech" },
  MSFT: { name: "Microsoft", sector: "Tech" },
  NVDA: { name: "NVIDIA", sector: "Tech" },
  GOOGL: { name: "Alphabet", sector: "Tech" },
  AMZN: { name: "Amazon", sector: "Tech" },
  META: { name: "Meta", sector: "Tech" },
  AVGO: { name: "Broadcom", sector: "Tech" },
  TSLA: { name: "Tesla", sector: "Tech" },
  // ============ LARGE CAP TECH ============
  AMD: { name: "AMD", sector: "Tech" },
  ADBE: { name: "Adobe", sector: "Tech" },
  CRM: { name: "Salesforce", sector: "Tech" },
  ORCL: { name: "Oracle", sector: "Tech" },
  INTC: { name: "Intel", sector: "Tech" },
  CSCO: { name: "Cisco", sector: "Tech" },
  NFLX: { name: "Netflix", sector: "Tech" },
  QCOM: { name: "Qualcomm", sector: "Tech" },
  TXN: { name: "Texas Instruments", sector: "Tech" },
  MU: { name: "Micron", sector: "Tech" },
  AMAT: { name: "Applied Materials", sector: "Tech" },
  LRCX: { name: "Lam Research", sector: "Tech" },
  KLAC: { name: "KLA Corp", sector: "Tech" },
  ARM: { name: "ARM Holdings", sector: "Tech" },
  MRVL: { name: "Marvell", sector: "Tech" },
  ASML: { name: "ASML", sector: "Tech" },
  TSM: { name: "Taiwan Semi", sector: "Tech" },
  DELL: { name: "Dell", sector: "Tech" },
  HPE: { name: "HPE", sector: "Tech" },
  IBM: { name: "IBM", sector: "Tech" },
  // ============ FINANCIALS ============
  "BRK-B": { name: "Berkshire B", sector: "Finance" },
  V: { name: "Visa", sector: "Finance" },
  JPM: { name: "JPMorgan", sector: "Finance" },
  BAC: { name: "Bank of America", sector: "Finance" },
  WFC: { name: "Wells Fargo", sector: "Finance" },
  GS: { name: "Goldman Sachs", sector: "Finance" },
  MS: { name: "Morgan Stanley", sector: "Finance" },
  MA: { name: "Mastercard", sector: "Finance" },
  AXP: { name: "American Express", sector: "Finance" },
  C: { name: "Citigroup", sector: "Finance" },
  SCHW: { name: "Schwab", sector: "Finance" },
  BLK: { name: "BlackRock", sector: "Finance" },
  SPGI: { name: "S&P Global", sector: "Finance" },
  COF: { name: "Capital One", sector: "Finance" },
  USB: { name: "US Bancorp", sector: "Finance" },
  PNC: { name: "PNC", sector: "Finance" },
  TFC: { name: "Truist", sector: "Finance" },
  // ============ HEALTHCARE ============
  UNH: { name: "UnitedHealth", sector: "Health" },
  JNJ: { name: "J&J", sector: "Health" },
  LLY: { name: "Eli Lilly", sector: "Health" },
  MRK: { name: "Merck", sector: "Health" },
  PFE: { name: "Pfizer", sector: "Health" },
  ABBV: { name: "AbbVie", sector: "Health" },
  TMO: { name: "Thermo Fisher", sector: "Health" },
  ABT: { name: "Abbott", sector: "Health" },
  AMGN: { name: "Amgen", sector: "Health" },
  GILD: { name: "Gilead", sector: "Health" },
  ISRG: { name: "Intuitive Surg", sector: "Health" },
  DHR: { name: "Danaher", sector: "Health" },
  BMY: { name: "Bristol-Myers", sector: "Health" },
  MDT: { name: "Medtronic", sector: "Health" },
  CVS: { name: "CVS Health", sector: "Health" },
  CI: { name: "Cigna", sector: "Health" },
  HUM: { name: "Humana", sector: "Health" },
  // ============ ENERGY ============
  XOM: { name: "Exxon Mobil", sector: "Energy" },
  CVX: { name: "Chevron", sector: "Energy" },
  COP: { name: "ConocoPhillips", sector: "Energy" },
  SLB: { name: "Schlumberger", sector: "Energy" },
  EOG: { name: "EOG Resources", sector: "Energy" },
  OXY: { name: "Occidental", sector: "Energy" },
  DVN: { name: "Devon Energy", sector: "Energy" },
  MPC: { name: "Marathon Petro", sector: "Energy" },
  VLO: { name: "Valero", sector: "Energy" },
  PSX: { name: "Phillips 66", sector: "Energy" },
  // ============ CONSUMER ============
  HD: { name: "Home Depot", sector: "Consumer" },
  LOW: { name: "Lowe's", sector: "Consumer" },
  COST: { name: "Costco", sector: "Consumer" },
  WMT: { name: "Walmart", sector: "Consumer" },
  TGT: { name: "Target", sector: "Consumer" },
  PG: { name: "P&G", sector: "Consumer" },
  KO: { name: "Coca-Cola", sector: "Consumer" },
  PEP: { name: "PepsiCo", sector: "Consumer" },
  MCD: { name: "McDonald's", sector: "Consumer" },
  SBUX: { name: "Starbucks", sector: "Consumer" },
  NKE: { name: "Nike", sector: "Consumer" },
  TJX: { name: "TJX", sector: "Consumer" },
  ROSS: { name: "Ross Stores", sector: "Consumer" },
  DG: { name: "Dollar General", sector: "Consumer" },
  DLTR: { name: "Dollar Tree", sector: "Consumer" },
  LULU: { name: "Lululemon", sector: "Consumer" },
  DECK: { name: "Deckers", sector: "Consumer" },
  CMG: { name: "Chipotle", sector: "Consumer" },
  WING: { name: "Wingstop", sector: "Consumer" },
  DPZ: { name: "Domino's", sector: "Consumer" },
  SHAK: { name: "Shake Shack", sector: "Consumer" },
  CAVA: { name: "Cava", sector: "Consumer" },
  BROS: { name: "Dutch Bros", sector: "Consumer" },
  CHWY: { name: "Chewy", sector: "Consumer" },
  ETSY: { name: "Etsy", sector: "Consumer" },
  W: { name: "Wayfair", sector: "Consumer" },
  // ============ INDUSTRIAL ============
  CAT: { name: "Caterpillar", sector: "Industrial" },
  DE: { name: "John Deere", sector: "Industrial" },
  HON: { name: "Honeywell", sector: "Industrial" },
  UPS: { name: "UPS", sector: "Industrial" },
  UNP: { name: "Union Pacific", sector: "Industrial" },
  RTX: { name: "RTX Corp", sector: "Industrial" },
  LMT: { name: "Lockheed", sector: "Industrial" },
  BA: { name: "Boeing", sector: "Industrial" },
  GE: { name: "GE Aerospace", sector: "Industrial" },
  MMM: { name: "3M", sector: "Industrial" },
  FDX: { name: "FedEx", sector: "Industrial" },
  // ============ MEDIA/TELECOM ============
  DIS: { name: "Disney", sector: "Media" },
  CMCSA: { name: "Comcast", sector: "Media" },
  T: { name: "AT&T", sector: "Media" },
  VZ: { name: "Verizon", sector: "Media" },
  TMUS: { name: "T-Mobile", sector: "Media" },
  CHTR: { name: "Charter", sector: "Media" },
  SNAP: { name: "Snap", sector: "Media" },
  PINS: { name: "Pinterest", sector: "Media" },
  SPOT: { name: "Spotify", sector: "Media" },
  ROKU: { name: "Roku", sector: "Media" },
  PARA: { name: "Paramount", sector: "Media" },
  WBD: { name: "Warner Bros", sector: "Media" },
  SIRI: { name: "Sirius XM", sector: "Media" },
  // ============ CLOUD/SAAS ============
  SNOW: { name: "Snowflake", sector: "Cloud" },
  DDOG: { name: "Datadog", sector: "Cloud" },
  NET: { name: "Cloudflare", sector: "Cloud" },
  CRWD: { name: "CrowdStrike", sector: "Cloud" },
  PANW: { name: "Palo Alto", sector: "Cloud" },
  ZS: { name: "Zscaler", sector: "Cloud" },
  OKTA: { name: "Okta", sector: "Cloud" },
  MDB: { name: "MongoDB", sector: "Cloud" },
  WDAY: { name: "Workday", sector: "Cloud" },
  NOW: { name: "ServiceNow", sector: "Cloud" },
  TEAM: { name: "Atlassian", sector: "Cloud" },
  HUBS: { name: "HubSpot", sector: "Cloud" },
  FTNT: { name: "Fortinet", sector: "Cloud" },
  S: { name: "SentinelOne", sector: "Cloud" },
  DOCN: { name: "DigitalOcean", sector: "Cloud" },
  CFLT: { name: "Confluent", sector: "Cloud" },
  ESTC: { name: "Elastic", sector: "Cloud" },
  GTLB: { name: "GitLab", sector: "Cloud" },
  MNDY: { name: "Monday.com", sector: "Cloud" },
  // ============ FINTECH ============
  SQ: { name: "Block", sector: "Fintech" },
  PYPL: { name: "PayPal", sector: "Fintech" },
  AFRM: { name: "Affirm", sector: "Fintech" },
  UPST: { name: "Upstart", sector: "Fintech" },
  BILL: { name: "Bill.com", sector: "Fintech" },
  COIN: { name: "Coinbase", sector: "Fintech" },
  SOFI: { name: "SoFi", sector: "Fintech" },
  HOOD: { name: "Robinhood", sector: "Fintech" },
  NU: { name: "Nu Holdings", sector: "Fintech" },
  // ============ E-COMMERCE ============
  SHOP: { name: "Shopify", sector: "E-comm" },
  UBER: { name: "Uber", sector: "E-comm" },
  LYFT: { name: "Lyft", sector: "E-comm" },
  DASH: { name: "DoorDash", sector: "E-comm" },
  ABNB: { name: "Airbnb", sector: "E-comm" },
  BKNG: { name: "Booking", sector: "E-comm" },
  EXPE: { name: "Expedia", sector: "E-comm" },
  // ============ SEMIS ============
  SMCI: { name: "Super Micro", sector: "Semis" },
  ON: { name: "ON Semi", sector: "Semis" },
  MPWR: { name: "Monolithic Pwr", sector: "Semis" },
  SNPS: { name: "Synopsys", sector: "Semis" },
  CDNS: { name: "Cadence", sector: "Semis" },
  WOLF: { name: "Wolfspeed", sector: "Semis" },
  ACLS: { name: "Axcelis", sector: "Semis" },
  ALGM: { name: "Allegro Micro", sector: "Semis" },
  FORM: { name: "FormFactor", sector: "Semis" },
  CRUS: { name: "Cirrus Logic", sector: "Semis" },
  SWKS: { name: "Skyworks", sector: "Semis" },
  QRVO: { name: "Qorvo", sector: "Semis" },
  // ============ EV/CLEAN ENERGY ============
  RIVN: { name: "Rivian", sector: "EV" },
  LCID: { name: "Lucid", sector: "EV" },
  NIO: { name: "NIO", sector: "EV" },
  XPEV: { name: "XPeng", sector: "EV" },
  LI: { name: "Li Auto", sector: "EV" },
  NKLA: { name: "Nikola", sector: "EV" },
  EVGO: { name: "EVgo", sector: "EV" },
  CHPT: { name: "ChargePoint", sector: "EV" },
  BLNK: { name: "Blink", sector: "EV" },
  ENPH: { name: "Enphase", sector: "Clean" },
  FSLR: { name: "First Solar", sector: "Clean" },
  SEDG: { name: "SolarEdge", sector: "Clean" },
  RUN: { name: "Sunrun", sector: "Clean" },
  NOVA: { name: "Sunnova", sector: "Clean" },
  // ============ AI/ML ============
  PLTR: { name: "Palantir", sector: "AI" },
  PATH: { name: "UiPath", sector: "AI" },
  AI: { name: "C3.ai", sector: "AI" },
  BBAI: { name: "BigBear.ai", sector: "AI" },
  SOUN: { name: "SoundHound", sector: "AI" },
  BIGC: { name: "BigCommerce", sector: "AI" },
  DOCS: { name: "Doximity", sector: "AI" },
  HIMS: { name: "Hims & Hers", sector: "AI" },
  OSCR: { name: "Oscar Health", sector: "AI" },
  // ============ GAMING ============
  RBLX: { name: "Roblox", sector: "Gaming" },
  U: { name: "Unity", sector: "Gaming" },
  TTWO: { name: "Take-Two", sector: "Gaming" },
  EA: { name: "EA", sector: "Gaming" },
  DKNG: { name: "DraftKings", sector: "Gaming" },
  PENN: { name: "Penn Gaming", sector: "Gaming" },
  RSI: { name: "Rush Street", sector: "Gaming" },
  // ============ QUANTUM ============
  IONQ: { name: "IonQ", sector: "Quantum" },
  RGTI: { name: "Rigetti", sector: "Quantum" },
  QBTS: { name: "D-Wave", sector: "Quantum" },
  // ============ MEME/RETAIL FAVORITES ============
  GME: { name: "GameStop", sector: "Meme" },
  AMC: { name: "AMC", sector: "Meme" },
  BBBY: { name: "Bed Bath", sector: "Meme" },
  KOSS: { name: "Koss", sector: "Meme" },
  BB: { name: "BlackBerry", sector: "Meme" },
  EXPR: { name: "Express", sector: "Meme" },
  CLOV: { name: "Clover Health", sector: "Meme" },
  WISH: { name: "ContextLogic", sector: "Meme" },
  WKHS: { name: "Workhorse", sector: "Meme" },
  GOEV: { name: "Canoo", sector: "Meme" },
  MULN: { name: "Mullen Auto", sector: "Meme" },
  FFIE: { name: "Faraday Future", sector: "Meme" },
  CVNA: { name: "Carvana", sector: "Meme" },
  OPEN: { name: "Opendoor", sector: "Meme" },
  // ============ CRYPTO ADJACENT ============
  MARA: { name: "Marathon Digital", sector: "Crypto" },
  RIOT: { name: "Riot Platforms", sector: "Crypto" },
  MSTR: { name: "MicroStrategy", sector: "Crypto" },
  CLSK: { name: "CleanSpark", sector: "Crypto" },
  HUT: { name: "Hut 8", sector: "Crypto" },
  BITF: { name: "Bitfarms", sector: "Crypto" },
  BTBT: { name: "Bit Digital", sector: "Crypto" },
  HIVE: { name: "HIVE Digital", sector: "Crypto" },
  // ============ LIDAR/TECH SPECULATIVE ============
  LAZR: { name: "Luminar", sector: "Lidar" },
  LIDR: { name: "AEye", sector: "Lidar" },
  MVIS: { name: "MicroVision", sector: "Lidar" },
  VUZI: { name: "Vuzix", sector: "Lidar" },
  // ============ TRAVEL/LEISURE ============
  CCL: { name: "Carnival", sector: "Travel" },
  AAL: { name: "American Air", sector: "Travel" },
  DAL: { name: "Delta", sector: "Travel" },
  UAL: { name: "United Air", sector: "Travel" },
  // ============ MATERIALS/MINING ============
  GOLD: { name: "Barrick Gold", sector: "Mining" },
  NEM: { name: "Newmont", sector: "Mining" },
  FCX: { name: "Freeport", sector: "Mining" },
  CLF: { name: "Cleveland-Cliffs", sector: "Mining" },
  X: { name: "US Steel", sector: "Mining" },
  AA: { name: "Alcoa", sector: "Mining" },
  VALE: { name: "Vale", sector: "Mining" },
  // ============ AUTO ============
  F: { name: "Ford", sector: "Auto" },
  GM: { name: "GM", sector: "Auto" },
};

// Sector categories with icons
const SECTORS: Record<string, { icon: React.ElementType; color: string }> = {
  Tech: { icon: Cpu, color: "text-blue-500" },
  Finance: { icon: Building2, color: "text-green-500" },
  Health: { icon: Heart, color: "text-pink-500" },
  Energy: { icon: Fuel, color: "text-orange-500" },
  Consumer: { icon: ShoppingCart, color: "text-purple-500" },
  Industrial: { icon: Factory, color: "text-gray-500" },
  Media: { icon: Tv, color: "text-cyan-500" },
  Cloud: { icon: Zap, color: "text-yellow-500" },
  Fintech: { icon: Zap, color: "text-emerald-500" },
  "E-comm": { icon: ShoppingCart, color: "text-indigo-500" },
  Semis: { icon: Cpu, color: "text-violet-500" },
  EV: { icon: Zap, color: "text-lime-500" },
  Clean: { icon: Zap, color: "text-teal-500" },
  AI: { icon: Cpu, color: "text-fuchsia-500" },
  Gaming: { icon: Zap, color: "text-rose-500" },
  Quantum: { icon: Zap, color: "text-sky-500" },
  Meme: { icon: Flame, color: "text-red-500" },
  Crypto: { icon: Zap, color: "text-amber-500" },
  Lidar: { icon: Zap, color: "text-slate-500" },
  Travel: { icon: Zap, color: "text-blue-400" },
  Mining: { icon: Factory, color: "text-stone-500" },
  Auto: { icon: Zap, color: "text-zinc-500" },
};

interface TickerSelectorProps {
  selectedTicker: string;
  onTickerChange: (ticker: string) => void;
  watchlist: string[];
  activeSignal?: {
    ticker: string;
    action: string;
    confidence: number;
  };
  className?: string;
}

export function TickerSelector({
  selectedTicker,
  onTickerChange,
  watchlist,
  activeSignal,
  className,
}: TickerSelectorProps) {
  const [searchValue, setSearchValue] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Filter and group tickers
  const { filtered, grouped } = useMemo(() => {
    const search = searchValue.toLowerCase().trim();

    // Filter by search
    const matchingTickers = watchlist.filter((ticker) => {
      if (!search) return true;
      const info = TICKER_INFO[ticker];
      return (
        ticker.toLowerCase().includes(search) ||
        info?.name.toLowerCase().includes(search) ||
        info?.sector.toLowerCase().includes(search)
      );
    });

    // Group by sector
    const groups: Record<string, string[]> = {};
    matchingTickers.forEach((ticker) => {
      const sector = TICKER_INFO[ticker]?.sector || "Other";
      if (!groups[sector]) groups[sector] = [];
      groups[sector].push(ticker);
    });

    return { filtered: matchingTickers, grouped: groups };
  }, [watchlist, searchValue]);

  // Get current ticker info
  const currentInfo = TICKER_INFO[selectedTicker];

  const handleSelect = (ticker: string) => {
    onTickerChange(ticker);
    setSearchValue("");
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      {/* Search Input */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          value={isOpen ? searchValue : selectedTicker}
          onChange={(e) => {
            setSearchValue(e.target.value.toUpperCase());
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          placeholder="Search ticker, name, or sector..."
          className="pl-10 pr-24 bg-secondary/50"
        />
        {/* Current ticker badge */}
        {!isOpen && currentInfo && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1">
            <span className="text-xs text-muted-foreground truncate max-w-[80px]">
              {currentInfo.name}
            </span>
            <Badge variant="outline" className="text-[10px] px-1.5">
              {currentInfo.sector}
            </Badge>
          </div>
        )}
      </div>

      {/* Dropdown */}
      {isOpen && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-popover border rounded-lg shadow-xl z-50 overflow-hidden">
          {/* Category tabs */}
          <div className="flex items-center gap-1 p-2 border-b bg-muted/30 overflow-x-auto">
            <button
              onClick={() => setActiveCategory(null)}
              className={cn(
                "px-2 py-1 rounded text-xs font-medium transition-colors whitespace-nowrap",
                activeCategory === null
                  ? "bg-primary text-primary-foreground"
                  : "hover:bg-accent"
              )}
            >
              All ({filtered.length})
            </button>
            {Object.keys(grouped).slice(0, 8).map((sector) => {
              const sectorInfo = SECTORS[sector];
              return (
                <button
                  key={sector}
                  onClick={() => setActiveCategory(activeCategory === sector ? null : sector)}
                  className={cn(
                    "px-2 py-1 rounded text-xs font-medium transition-colors whitespace-nowrap flex items-center gap-1",
                    activeCategory === sector
                      ? "bg-primary text-primary-foreground"
                      : "hover:bg-accent"
                  )}
                >
                  {sectorInfo && <sectorInfo.icon className={cn("h-3 w-3", activeCategory !== sector && sectorInfo.color)} />}
                  {sector} ({grouped[sector]?.length || 0})
                </button>
              );
            })}
          </div>

          {/* Active Signal - shown at top when there's an active trade decision */}
          {activeSignal && (
            <div className={cn(
              "p-2 border-b",
              activeSignal.action === "BUY" && "bg-gradient-to-r from-green-500/20 to-emerald-500/10",
              activeSignal.action === "SELL" && "bg-gradient-to-r from-red-500/20 to-rose-500/10",
              activeSignal.action === "HOLD" && "bg-gradient-to-r from-yellow-500/10 to-orange-500/10"
            )}>
              <div className="flex items-center justify-between mb-1.5 px-1">
                <div className="flex items-center gap-2">
                  <Flame className={cn(
                    "h-3.5 w-3.5 animate-pulse",
                    activeSignal.action === "BUY" && "text-green-500",
                    activeSignal.action === "SELL" && "text-red-500",
                    activeSignal.action === "HOLD" && "text-yellow-500"
                  )} />
                  <span className={cn(
                    "text-xs font-semibold uppercase tracking-wide",
                    activeSignal.action === "BUY" && "text-green-500",
                    activeSignal.action === "SELL" && "text-red-500",
                    activeSignal.action === "HOLD" && "text-yellow-500"
                  )}>
                    Trade Decision: {activeSignal.action}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">
                  Signal strength: {Math.round(activeSignal.confidence * 100)}/100
                </span>
              </div>
              <button
                onClick={() => handleSelect(activeSignal.ticker)}
                className={cn(
                  "w-full px-3 py-2 rounded-md text-sm font-bold transition-all flex items-center justify-between",
                  "hover:scale-[1.01]",
                  activeSignal.action === "BUY" && "bg-green-500/20 ring-1 ring-green-500/50 text-green-500",
                  activeSignal.action === "SELL" && "bg-red-500/20 ring-1 ring-red-500/50 text-red-500",
                  activeSignal.action === "HOLD" && "bg-yellow-500/20 ring-1 ring-yellow-500/50 text-yellow-500",
                  activeSignal.ticker === selectedTicker && "ring-2 ring-offset-1 ring-offset-background"
                )}
              >
                <div className="flex items-center gap-2">
                  <Flame className="h-4 w-4" />
                  <span className="text-lg">{activeSignal.ticker}</span>
                  {TICKER_INFO[activeSignal.ticker] && (
                    <span className="text-xs opacity-70">
                      {TICKER_INFO[activeSignal.ticker].name}
                    </span>
                  )}
                </div>
                <span className="text-xs font-normal opacity-70">
                  Click to analyze
                </span>
              </button>
            </div>
          )}

          {/* Ticker grid */}
          <ScrollArea className="h-[320px]">
            {activeCategory ? (
              // Single category view
              <div className="p-2">
                <div className="flex flex-wrap gap-1">
                  {grouped[activeCategory]?.map((ticker) => (
                    <TickerChip
                      key={ticker}
                      ticker={ticker}
                      isSelected={ticker === selectedTicker}
                      isActiveSignal={ticker === activeSignal?.ticker}
                      onClick={() => handleSelect(ticker)}
                    />
                  ))}
                </div>
              </div>
            ) : (
              // Grouped view
              <div className="p-2 space-y-3">
                {Object.entries(grouped).map(([sector, tickers]) => {
                  const sectorInfo = SECTORS[sector];
                  return (
                    <div key={sector}>
                      <div className="flex items-center gap-2 mb-1.5 px-1">
                        {sectorInfo && <sectorInfo.icon className={cn("h-3.5 w-3.5", sectorInfo.color)} />}
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                          {sector}
                        </span>
                        <span className="text-[10px] text-muted-foreground">({tickers.length})</span>
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {tickers.map((ticker) => (
                          <TickerChip
                            key={ticker}
                            ticker={ticker}
                            isSelected={ticker === selectedTicker}
                            isActiveSignal={ticker === activeSignal?.ticker}
                            onClick={() => handleSelect(ticker)}
                          />
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </ScrollArea>

          {/* Quick stats footer */}
          <div className="flex items-center justify-between p-2 border-t bg-muted/30 text-xs text-muted-foreground">
            <span>{filtered.length} tickers available</span>
            <span>Type to search by name or sector</span>
          </div>
        </div>
      )}
    </div>
  );
}

// Individual ticker chip component
function TickerChip({
  ticker,
  isSelected,
  isActiveSignal,
  onClick,
}: {
  ticker: string;
  isSelected: boolean;
  isActiveSignal?: boolean;
  onClick: () => void;
}) {
  const info = TICKER_INFO[ticker];

  return (
    <button
      onClick={onClick}
      className={cn(
        "group relative px-2.5 py-1.5 rounded-md text-sm font-medium transition-all",
        "hover:bg-accent hover:scale-105",
        isActiveSignal && !isSelected && "bg-gradient-to-r from-yellow-500/20 to-orange-500/20 ring-1 ring-orange-500/50",
        isSelected
          ? "bg-primary text-primary-foreground ring-2 ring-primary ring-offset-1 ring-offset-background"
          : !isActiveSignal && "bg-secondary/50"
      )}
    >
      <div className="flex items-center gap-1.5">
        {isActiveSignal && <Flame className="h-3 w-3 text-orange-500" />}
        <span className="font-bold">{ticker}</span>
        {info && (
          <span className={cn(
            "text-[10px] opacity-70 group-hover:opacity-100 transition-opacity hidden sm:inline",
            isSelected ? "text-primary-foreground/80" : "text-muted-foreground"
          )}>
            {info.name.length > 10 ? info.name.slice(0, 10) + "…" : info.name}
          </span>
        )}
      </div>
    </button>
  );
}
