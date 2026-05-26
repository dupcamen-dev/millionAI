"use client";

import { useState, useRef, useEffect } from "react";
import { apiGet, LogEntry, LogsData } from "@/lib/api";

const LEVELS: (string)[] = ["ALL", "SYS", "INFO", "EXEC", "WARN", "ERROR"];

const LEVEL_COLORS: Record<string, string> = {
  INFO: "text-on-surface-variant",
  SYS: "text-primary-fixed-dim",
  EXEC: "text-on-surface",
  WARN: "text-[#ffd5ae]",
  ERROR: "text-error",
};

export default function LogsPage() {
  const [allLogs, setAllLogs] = useState<LogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [levelFilter, setLevelFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const logContainerRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const params = new URLSearchParams({ limit: "200", offset: "0" });
        if (levelFilter !== "ALL") params.set("level", levelFilter);
        if (search) params.set("search", search);
        const data = await apiGet<LogsData>(`/api/v1/logs?${params}`);
        setAllLogs(data.logs);
        setTotal(data.total);
      } catch {
        console.error("Failed to load logs");
      }
    };
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [levelFilter, search]);

  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [allLogs.length, autoScroll]);

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleTimeString();
  };

  return (
    <>
      <div className="border-b border-surface-variant pb-unit-2 flex justify-between items-end">
        <div>
          <h1 className="font-headline-lg text-headline-lg text-on-surface uppercase">LOGS</h1>
          <p className="font-code-snippet text-code-snippet text-outline mt-unit-1">&gt; SYS.LOG_TAIL: {total} ENTRIES</p>
        </div>
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`font-label-caps text-label-caps px-unit-4 py-unit-2 border transition-colors uppercase ${
            autoScroll
              ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim"
              : "border-outline-variant text-outline"
          }`}
        >
          AUTO_SCROLL: {autoScroll ? "ON" : "OFF"}
        </button>
      </div>

      <div className="flex flex-col md:flex-row gap-unit-4 items-start md:items-center justify-between">
        <div className="flex gap-unit-2 font-label-caps text-label-caps flex-wrap">
          {LEVELS.map((lvl) => (
            <button
              key={lvl}
              onClick={() => setLevelFilter(lvl)}
              className={`px-unit-4 py-unit-2 border transition-colors uppercase ${
                levelFilter === lvl
                  ? "bg-primary-fixed-dim text-on-primary border-primary-fixed-dim"
                  : "border-outline-variant text-outline hover:border-primary-fixed-dim"
              }`}
            >
              {lvl}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="bg-black border border-outline-variant text-on-surface font-code-snippet text-code-snippet px-unit-4 py-unit-2 focus:border-primary-fixed-dim focus:outline-none transition-colors w-full md:w-64"
          placeholder="Search logs..."
        />
      </div>

      <div className="border border-surface-variant bg-background">
        <div className="p-unit-2 border-b border-surface-variant bg-surface-container-low font-code-snippet text-code-snippet text-outline flex items-center gap-unit-4 uppercase">
          <span className="w-16 shrink-0">TIME</span>
          <span className="w-16 shrink-0">LEVEL</span>
          <span className="flex-1">MESSAGE</span>
        </div>
        <div ref={logContainerRef} className="h-[500px] overflow-y-auto font-code-snippet text-code-snippet">
          {allLogs.length === 0 ? (
            <div className="p-unit-8 text-center text-outline">&gt; NO LOGS MATCH FILTER</div>
          ) : (
            allLogs.map((log, i) => (
              <div
                key={log.id || i}
                className="flex items-start gap-unit-4 px-unit-4 py-unit-2 border-b border-surface-variant hover:bg-surface-container-low transition-colors"
              >
                <span className="text-outline w-16 shrink-0">{formatTime(log.created_at)}</span>
                <span className={`${LEVEL_COLORS[log.level] || "text-on-surface-variant"} w-16 shrink-0 font-bold uppercase`}>
                  {log.level}
                </span>
                <span className={`flex-1 ${log.level === "ERROR" ? "text-error" : ""}`}>
                  &gt; {log.message}
                </span>
              </div>
            ))
          )}
        </div>
        <div className="p-unit-2 border-t border-surface-variant bg-surface-container-low font-code-snippet text-code-snippet text-outline text-right">
          {allLogs.length} / {total} ENTRIES
        </div>
      </div>
    </>
  );
}
