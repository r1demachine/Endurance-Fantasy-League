"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { authApi } from "@/lib/auth";
import Link from "next/link";

type ModalKind = null | "search" | "list";
type Tab = "friends" | "clubs";

interface Person {
  id: number;
  username: string;
  display_name: string;
  level: number;
  total_xp: number;
  relation?: "friends" | "sent" | "incoming" | null;
  friendship_id?: number | null;
}

/* ── Оболочка модалки: затемнение + кнопка назад ── */
function ModalShell({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[80] bg-black/70 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <motion.div
        initial={{ y: 28, scale: 0.97 }}
        animate={{ y: 0, scale: 1 }}
        exit={{ y: 28, scale: 0.97 }}
        transition={{ duration: 0.2, ease: "easeOut" }}
        className="w-full max-w-md bg-[#f4f4f0] border-2 border-black shadow-[6px_6px_0_rgba(0,0,0,0.45)] max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b-2 border-black bg-[#5866f2] text-white px-4 py-3">
          <p className="font-display uppercase text-xl leading-none">{title}</p>
          <button
            onClick={onClose}
            className="px-3 py-2 border-2 border-black bg-white text-[#111] text-[10px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors"
          >
            ← Back
          </button>
        </div>
        <div className="overflow-y-auto p-4">{children}</div>
      </motion.div>
    </motion.div>
  );
}

/* ── Строка атлета ── */
function PersonRow({ p, action, href }: { p: Person; action?: ReactNode; href?: string }) {
  const body = (
    <>
      <span className="w-9 h-9 shrink-0 bg-[#171a38] text-white flex items-center justify-center font-display lowercase text-lg">
        {p.display_name.charAt(0)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-bold uppercase tracking-wide text-sm truncate">{p.display_name}</p>
        <p className="text-[9px] font-bold tracking-widest uppercase text-[#666]">
          @{p.username} · LVL {p.level} · {Math.round(p.total_xp)} XP
        </p>
      </div>
    </>
  );
  return (
    <div className="flex items-center gap-3 border-2 border-black bg-white px-3 py-2">
      {href ? (
        <Link href={href} className="flex items-center gap-3 min-w-0 flex-1 hover:opacity-70 transition-opacity">
          {body}
        </Link>
      ) : (
        <div className="flex items-center gap-3 min-w-0 flex-1">{body}</div>
      )}
      {action}
    </div>
  );
}

/* ── Модалка поиска ── */
function SearchModal({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [searched, setSearched] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);

  const doSearch = async () => {
    if (q.trim().length < 2) return;
    try {
      const r = await authApi.get("/api/friends/search", { params: { q: q.trim() } });
      setResults(r.data.results);
      setSearched(true);
    } catch {}
  };

  const add = async (p: Person) => {
    setBusyId(p.id);
    try {
      const r = await authApi.post("/api/friends/add", { username: p.username });
      const newRel = r.data.status === "accepted" ? "friends" : "sent";
      setResults((prev) => prev.map((x) => (x.id === p.id ? { ...x, relation: newRel } : x)));
      onChanged();
    } catch (err: any) {
      alert(err.response?.data?.detail || "Ошибка заявки");
    } finally {
      setBusyId(null);
    }
  };

  const accept = async (p: Person) => {
    setBusyId(p.id);
    try {
      await authApi.post("/api/friends/accept", { friendship_id: p.friendship_id });
      setResults((prev) => prev.map((x) => (x.id === p.id ? { ...x, relation: "friends" } : x)));
      onChanged();
    } catch {} finally {
      setBusyId(null);
    }
  };

  const actionFor = (p: Person) => {
    switch (p.relation) {
      case "friends":
        return <span className="px-2 py-1 bg-[#5866f2] text-white text-[9px] font-bold tracking-widest uppercase shrink-0">Friends ✓</span>;
      case "sent":
        return <span className="px-2 py-1 border border-black/30 text-[#666] text-[9px] font-bold tracking-widest uppercase shrink-0">Requested</span>;
      case "incoming":
        return (
          <button
            onClick={() => accept(p)}
            disabled={busyId === p.id}
            className="px-3 py-2 bg-[#ffd500] border-2 border-black text-[9px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors shrink-0 disabled:opacity-50"
          >
            Accept
          </button>
        );
      default:
        return (
          <button
            onClick={() => add(p)}
            disabled={busyId === p.id}
            className="px-3 py-2 bg-[#ff4b26] text-white border-2 border-black text-[9px] font-bold tracking-widest uppercase hover:bg-black transition-colors shrink-0 disabled:opacity-50"
          >
            {busyId === p.id ? "..." : "Add +"}
          </button>
        );
    }
  };

  return (
    <ModalShell title="Find athletes" onClose={onClose}>
      <div className="flex gap-2 mb-4">
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doSearch()}
          placeholder="name or @username"
          className="flex-1 px-4 py-3 bg-white border-2 border-black font-bold text-sm focus:outline-none focus:bg-[#ffd500]/20 transition-colors"
        />
        <button
          onClick={doSearch}
          className="px-4 py-3 bg-[#ffd500] border-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors"
        >
          Search
        </button>
      </div>

      <div className="space-y-2">
        {results.map((p) => (
          <PersonRow key={p.id} p={p} action={actionFor(p)} href={`/u/${p.username}`} />
        ))}
        {searched && results.length === 0 && (
          <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">
            Nobody found 🌙 Try another name
          </p>
        )}
        {!searched && (
          <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">
            Search by name or login → add to friends
          </p>
        )}
      </div>
    </ModalShell>
  );
}

/* ── Модалка списка друзей ── */
function ListModal({ onClose, onChanged }: { onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<{ friends: Person[]; incoming: Person[]; outgoing: Person[] }>({
    friends: [],
    incoming: [],
    outgoing: [],
  });
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await authApi.get("/api/friends");
      setData(r.data);
    } catch {} finally {
      setLoaded(true);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const accept = async (p: Person) => {
    await authApi.post("/api/friends/accept", { friendship_id: p.friendship_id });
    load();
    onChanged();
  };
  const reject = async (p: Person) => {
    await authApi.post("/api/friends/reject", { friendship_id: p.friendship_id });
    load();
    onChanged();
  };

  return (
    <ModalShell title="My friends" onClose={onClose}>
      <div className="space-y-5">
        {/* Входящие заявки */}
        {data.incoming.length > 0 && (
          <div>
            <p className="text-[9px] font-bold tracking-widest uppercase text-[#ff4b26] mb-2">
              Incoming requests · {data.incoming.length}
            </p>
            <div className="space-y-2">
              {data.incoming.map((p) => (
                <PersonRow
                  key={p.id}
                  p={p}
                  action={
                    <span className="flex gap-1 shrink-0">
                      <button onClick={() => accept(p)} className="px-2 py-2 bg-[#ffd500] border-2 border-black text-[9px] font-bold tracking-widest uppercase hover:bg-black hover:text-white">✓</button>
                      <button onClick={() => reject(p)} className="px-2 py-2 bg-white border-2 border-black text-[9px] font-bold tracking-widest uppercase hover:bg-[#ff4b26] hover:text-white">✕</button>
                    </span>
                  }
                />
              ))}
            </div>
          </div>
        )}

        {/* Друзья */}
        <div>
          <p className="text-[9px] font-bold tracking-widest uppercase text-[#666] mb-2">Friends · {data.friends.length}</p>
          <div className="space-y-2">
            {data.friends.map((p) => (
              <PersonRow key={p.id} p={p} action={<span className="font-display text-[#ff4b26] shrink-0">{Math.round(p.total_xp).toLocaleString()}</span>} href={`/u/${p.username}`} />
            ))}
            {data.friends.length === 0 && (
              <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-4">
                No friends yet — find athletes in search 🔍
              </p>
            )}
          </div>
        </div>

        {/* Исходящие */}
        {data.outgoing.length > 0 && (
          <div>
            <p className="text-[9px] font-bold tracking-widest uppercase text-[#666] mb-2">Requested</p>
            <div className="space-y-2">
              {data.outgoing.map((p) => (
                <PersonRow key={p.id} p={p} action={<span className="px-2 py-1 border border-black/30 text-[#666] text-[9px] font-bold tracking-widest uppercase shrink-0">Pending</span>} />
              ))}
            </div>
          </div>
        )}

        {!loaded && <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">Loading...</p>}
      </div>
    </ModalShell>
  );
}

/* ── Панель друзей: 2 кнопки ── */
function FriendsPanel({ version, onOpen }: { version: number; onOpen: (m: "search" | "list") => void }) {
  const [incoming, setIncoming] = useState(0);
  const [friendsCount, setFriendsCount] = useState<number | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await authApi.get("/api/friends");
        setIncoming(r.data.incoming?.length ?? 0);
        setFriendsCount(r.data.friends?.length ?? 0);
      } catch {}
    })();
  }, [version]);

  return (
    <div className="p-5 md:p-6">
      <div className="grid sm:grid-cols-2 gap-3">
        <button
          onClick={() => onOpen("search")}
          className="border-2 border-black bg-white px-4 py-4 flex items-center justify-between gap-3 hover:bg-[#ffd500] transition-colors"
        >
          <span className="text-[11px] font-bold tracking-widest uppercase">Find athletes</span>
          <span className="font-display text-2xl">🔍</span>
        </button>
        <button
          onClick={() => onOpen("list")}
          className="relative border-2 border-black bg-white px-4 py-4 flex items-center justify-between gap-3 hover:bg-[#ffd500] transition-colors"
        >
          <span className="text-[11px] font-bold tracking-widest uppercase">
            My friends{friendsCount !== null ? ` (${friendsCount})` : ""}
          </span>
          <span className="font-display text-2xl">👥</span>
          {incoming > 0 && (
            <span className="absolute -top-3 -right-3 w-7 h-7 bg-[#ff4b26] text-white border-2 border-black flex items-center justify-center text-[10px] font-bold rounded-full">
              {incoming}
            </span>
          )}
        </button>
      </div>
      <p className="text-[10px] font-bold tracking-widest uppercase text-[#666] mt-4">
        Friends compete in the Friends rating on your dashboard
      </p>
    </div>
  );
}

/* ── Заглушка клубов ── */
function ClubsStub() {
  return (
    <div className="p-5 md:p-6">
      <div className="border-2 border-dashed border-black/40 bg-white px-4 py-8 text-center">
        <p className="font-display uppercase text-3xl md:text-4xl">Clubs</p>
        <p className="text-[10px] font-bold tracking-widest uppercase text-[#666] mt-2">coming soon 🚧</p>
        <p className="text-sm text-[#666] mt-4 max-w-sm mx-auto">
          Создавай свой вело-клуб, зови друзей и соревнуйтесь командным рейтингом — в следующем обновлении.
        </p>
      </div>
    </div>
  );
}

/* ── Сам контейнер Social ── */
export default function SocialHub() {
  const [tab, setTab] = useState<Tab>("friends");
  const [modal, setModal] = useState<ModalKind>(null);
  const [version, setVersion] = useState(0);
  const bump = () => setVersion((v) => v + 1);

  return (
    <div className="border-b-2 border-black">
      <div className="grid md:grid-cols-[200px_1fr]">
        {/* Сайдбар */}
        <div className="hidden md:flex flex-col justify-between p-5 border-r-2 border-black bg-[#ffd500] text-[#111]">
          <div>
            <p className="font-display uppercase text-xl md:text-2xl tracking-tight leading-none">Social</p>
            <div className="h-0.5 bg-black mt-3 mb-4"></div>
            <p className="block text-[#111]/70 text-[10px] font-bold tracking-widest uppercase">Friends & Clubs</p>
          </div>
          <span className="font-display text-4xl mt-auto">↓</span>
        </div>

        <div>
          {/* Мобильный заголовок */}
          <div className="md:hidden">
            <div className="px-4 py-3 border-b-2 border-black bg-[#ffd500] text-[#111] font-display uppercase text-xl tracking-tight">
              Social
            </div>
          </div>

          {/* Вкладки */}
          <div className="flex border-b-2 border-black">
            <button
              onClick={() => setTab("friends")}
              className={`flex-1 px-4 py-3 text-[10px] md:text-xs font-bold tracking-widest uppercase transition-colors ${
                tab === "friends" ? "bg-[#ffd500] text-[#111]" : "hover:bg-black/5"
              }`}
            >
              Friends
            </button>
            <button
              onClick={() => setTab("clubs")}
              className={`flex-1 px-4 py-3 text-[10px] md:text-xs font-bold tracking-widest uppercase border-l-2 border-black transition-colors ${
                tab === "clubs" ? "bg-[#ffd500] text-[#111]" : "hover:bg-black/5"
              }`}
            >
              Clubs
            </button>
          </div>

          {tab === "friends" ? <FriendsPanel version={version} onOpen={setModal} /> : <ClubsStub />}
        </div>
      </div>

      {/* Модалки */}
      <AnimatePresence>
        {modal === "search" && <SearchModal onClose={() => setModal(null)} onChanged={bump} />}
        {modal === "list" && <ListModal onClose={() => setModal(null)} onChanged={bump} />}
      </AnimatePresence>
    </div>
  );
}