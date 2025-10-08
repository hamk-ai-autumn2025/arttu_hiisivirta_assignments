"use client";
import { useState } from "react";

export default function Home() {
  const [text, setText] = useState("Budjetti 2000€, gravel, mukavuus tärkeää, pituus 178 cm");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);

  async function onSearch() {
    setLoading(true);
    const res = await fetch("http://localhost:8000/recommend", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    });
    const data = await res.json();
    setResults(data);
    setLoading(false);
  }
  return (
    <main className="p-6 max-w-3xl mx-auto">
      <h1 className="text-2xl font-semibold mb-2">Pyöräsuositukset (proto)</h1>
      <textarea className="w-full border rounded p-3 mb-3" rows={4}
        value={text} onChange={e => setText(e.target.value)} />
      <button onClick={onSearch} disabled={loading}
        className="px-4 py-2 rounded bg-black text-white">
        {loading ? "Haetaan..." : "Hae suositukset"}
      </button>

      {results && (
        <section className="mt-6 space-y-3">
          <h2 className="text-xl font-medium">Top 3</h2>
          {results.results.map((r: any, i: number) => (
            <div key={i} className="border rounded p-4">
              <div className="font-semibold">{r.brand} {r.model}</div>
              <p className="text-sm opacity-80">{r.reason}</p>
              {r.url && <a className="text-blue-600 underline" href={r.url} target="_blank">Tuotesivu</a>}
            </div>
          ))}
        </section>
      )}
    </main>
  );
}
