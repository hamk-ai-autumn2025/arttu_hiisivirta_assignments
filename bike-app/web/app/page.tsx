"use client";
import { useState } from "react";

type ResultItem = {
  brand: string;
  model: string;
  reason: string;
  url?: string;
  image_url?: string;
};

export default function Home() {
  const [text, setText] = useState("Gravel-pyörä noin 2000 €, mukavuus tärkeää, pituus 178 cm");
  const [discipline, setDiscipline] = useState<"" | "road" | "gravel">("");
  const [budget, setBudget] = useState<number | "">("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [results, setResults] = useState<ResultItem[] | null>(null);
  const [intent, setIntent] = useState<any>(null);

  async function onSearch(e?: React.FormEvent) {
    e?.preventDefault();
    setLoading(true);
    setErrorMsg(null);
    setResults(null);
    try {
      const res = await fetch("http://localhost:8000/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          max_price: budget === "" ? null : Number(budget),
          discipline: discipline || null
        })
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setIntent(data.intent ?? null);
      setResults(data.results ?? []);
    } catch (err: any) {
      setErrorMsg(err?.message || "Virhe haussa");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      {/* Header */}
      <header className="mb-6">
        <h1 className="text-3xl font-semibold">Pyöräsuositukset (proto)</h1>
        <p className="text-gray-600 mt-1">Kirjoita tarpeesi vapaasti – sovellus ehdottaa sopivia maantie- tai gravelpyöriä.</p>
      </header>

      {/* Card: Search */}
      <section className="bg-white rounded-2xl shadow p-5 mb-6">
        <form onSubmit={onSearch} className="grid gap-4 md:grid-cols-3">
          <div className="md:col-span-3">
            <label className="block text-sm font-medium text-gray-700 mb-1">Kuvaa tarpeesi</label>
            <textarea
              className="w-full rounded-lg border border-gray-300 p-3 focus:outline-none focus:ring-2 focus:ring-black"
              rows={3}
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Pyörätyyppi</label>
            <select
              className="w-full rounded-lg border border-gray-300 p-2.5"
              value={discipline}
              onChange={(e) => setDiscipline(e.target.value as any)}
            >
              <option value="">Ei väliä</option>
              <option value="road">Maantie</option>
              <option value="gravel">Gravel</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Budjetti (€)</label>
            <input
              className="w-full rounded-lg border border-gray-300 p-2.5"
              type="number"
              min={0}
              placeholder="esim. 2000"
              value={budget}
              onChange={(e) => setBudget(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </div>

          <div className="flex items-end">
            <button
              disabled={loading}
              className="inline-flex items-center justify-center rounded-lg bg-black px-5 py-2.5 text-white hover:opacity-90 disabled:opacity-60 w-full"
              type="submit"
            >
              {loading ? "Haetaan…" : "Hae suositukset"}
            </button>
          </div>
        </form>

        {/* Error banner */}
        {errorMsg && (
          <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-red-700">
            {errorMsg}
          </div>
        )}

        {/* Intent debug (optional) */}
        {intent && (
          <details className="mt-3 text-sm text-gray-600">
            <summary className="cursor-pointer select-none">Näytä tulkittu intent (debug)</summary>
            <pre className="mt-2 whitespace-pre-wrap break-all bg-gray-50 p-3 rounded-lg border">{JSON.stringify(intent, null, 2)}</pre>
          </details>
        )}
      </section>

      {/* Results */}
      <section>
        <h2 className="text-xl font-semibold mb-3">Tulokset</h2>

        {loading && (
          <div className="grid gap-4 md:grid-cols-3">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="animate-pulse rounded-2xl bg-white p-4 shadow">
                <div className="h-40 w-full rounded-lg bg-gray-200 mb-3" />
                <div className="h-4 w-2/3 bg-gray-200 rounded mb-2" />
                <div className="h-4 w-1/2 bg-gray-200 rounded mb-2" />
                <div className="h-4 w-3/4 bg-gray-200 rounded" />
              </div>
            ))}
          </div>
        )}

        {!loading && results && results.length > 0 && (
          <div className="grid gap-4 md:grid-cols-3">
            {results.map((r, i) => (
              <article key={i} className="rounded-2xl bg-white p-4 shadow border border-gray-100">
                <div className="aspect-video w-full overflow-hidden rounded-lg bg-gray-100 mb-3">
                  {/* fallback if no image */}
                  {r.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={r.image_url} alt={`${r.brand} ${r.model}`} className="h-full w-full object-cover" />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-gray-400">Ei kuvaa</div>
                  )}
                </div>

                <h3 className="text-lg font-semibold">{r.brand} {r.model}</h3>
                <p className="text-sm text-gray-700 mt-1">{r.reason}</p>

                <div className="mt-3">
                  {r.url && (
                    <a
                      href={r.url}
                      target="_blank"
                      className="inline-flex items-center rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50"
                    >
                      Tuotesivu →
                    </a>
                  )}
                </div>
              </article>
            ))}
          </div>
        )}

        {!loading && results && results.length === 0 && (
          <p className="text-gray-600">Ei tuloksia – lisää malleja tietokantaan tai laajenna hakuehtoja.</p>
        )}
      </section>
    </main>
  );
}
