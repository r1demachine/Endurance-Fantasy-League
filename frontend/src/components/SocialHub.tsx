"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { AnimatePresence } from "framer-motion";
import { authApi } from "@/lib/auth";
import Link from "next/link";
import { Modal, ConfirmDialog } from "@/components/Modal";
import { getApiErrorMessage } from "@/components/dialog-utils";

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
function SearchModal({ onClose, onChanged, onError }: { onClose: () => void; onChanged: () => void; onError: (message: string) => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [searched, setSearched] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searching, setSearching] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const performSearch = useCallback(async (query: string) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setSearching(true);
    setSearchError("");
    try {
      const r = await authApi.get("/api/friends/search", { params: { q: query }, signal: controller.signal });
      if (!controller.signal.aborted) {
        setResults(r.data.results || []);
        setSearched(true);
      }
    } catch (error: unknown) {
      const errorName = error && typeof error === "object" && "name" in error ? String(error.name) : "";
      if (!controller.signal.aborted && errorName !== "CanceledError" && errorName !== "AbortError") {
        setResults([]);
        setSearched(true);
        setSearchError(getApiErrorMessage(error, "Не удалось выполнить поиск друзей."));
      }
    } finally {
      if (!controller.signal.aborted) setSearching(false);
    }
  }, []);

  useEffect(() => {
    const query = q.trim();
    if (query.length < 2) {
      controllerRef.current?.abort();
      setResults([]);
      setSearched(false);
      setSearching(false);
      setSearchError("");
      return;
    }
    const timer = window.setTimeout(() => { void performSearch(query); }, 300);
    return () => {
      window.clearTimeout(timer);
      controllerRef.current?.abort();
    };
  }, [q, performSearch]);

  useEffect(() => {
    return () => {
      controllerRef.current?.abort();
    };
  }, []);

  const doSearch = () => {
    const query = q.trim();
    if (query.length >= 2) void performSearch(query);
  };

  const add = async (p: Person) => {
    setBusyId(p.id);
    try {
      const r = await authApi.post("/api/friends/add", { username: p.username });
      const newRel = r.data.status === "accepted" ? "friends" : "sent";
      setResults((prev) => prev.map((x) => (x.id === p.id ? { ...x, relation: newRel } : x)));
      onChanged();
    } catch (error: unknown) {
      onError(getApiErrorMessage(error, "Не удалось отправить заявку в друзья."));
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
    } catch (error: unknown) {
      onError(getApiErrorMessage(error, "Не удалось принять заявку в друзья."));
    } finally {
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
    <Modal title="Find athletes" onClose={onClose}>
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
          disabled={q.trim().length < 2 || searching}
          className="px-4 py-3 bg-[#ffd500] border-2 border-black text-[10px] font-bold tracking-widest uppercase hover:bg-black hover:text-white transition-colors disabled:opacity-50"
        >
          {searching ? "Searching…" : "Search"}
        </button>
      </div>

      <div className="space-y-2">
        {searchError && <p role="alert" className="border-l-4 border-[#ff4b26] bg-[#ff4b26]/10 px-3 py-2 text-sm font-bold text-[#a62910]">{searchError}</p>}
        {results.map((p) => (
          <PersonRow key={p.id} p={p} action={actionFor(p)} href={`/u/${p.username}`} />
        ))}
        {searched && results.length === 0 && (
          <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">
            Nobody found 🌙 Try another name
          </p>
        )}
        {searching && <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-3">Поиск…</p>}
        {!searched && !searching && (
          <p className="text-center text-[10px] font-bold tracking-widest uppercase text-[#666] py-6">
            Search by name or login → add to friends
          </p>
        )}
      </div>
    </Modal>
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
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await authApi.get("/api/friends");
      setData(r.data);
      setError("");
    } catch (error: unknown) {
      setError(getApiErrorMessage(error, "Не удалось загрузить список друзей."));
    } finally {
      setLoaded(true);
    }
  }, []);
  useEffect(() => {
    load();
  }, [load]);

  const updateRelation = async (p: Person, action: "accept" | "reject") => {
    if (p.friendship_id == null) {
      setError("Не удалось определить заявку. Обнови список и попробуй снова.");
      return;
    }
    setBusyId(p.id);
    setError("");
    try {
      await authApi.post("/api/friends/" + action, { friendship_id: p.friendship_id });
      await load();
      onChanged();
    } catch (error: unknown) {
      setError(getApiErrorMessage(error, action === "accept" ? "Не удалось принять заявку." : "Не удалось отклонить заявку."));
    } finally {
      setBusyId(null);
    }
  };
  const accept = (p: Person) => updateRelation(p, "accept");
  const reject = (p: Person) => updateRelation(p, "reject");

  return (
    <Modal title="My friends" onClose={onClose}>
      <div className="space-y-5">
        {error && <p role="alert" className="border-l-4 border-[#ff4b26] bg-[#ff4b26]/10 px-3 py-2 text-sm font-bold text-[#a62910]">{error}</p>}
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
                  href={`/u/${p.username}`}
                  action={
                    <span className="flex gap-1 shrink-0">
                      <button onClick={() => accept(p)} disabled={busyId === p.id} className="px-2 py-2 bg-[#ffd500] border-2 border-black text-[9px] font-bold tracking-widest uppercase hover:bg-black hover:text-white disabled:opacity-50">✓</button>
                      <button onClick={() => reject(p)} disabled={busyId === p.id} className="px-2 py-2 bg-white border-2 border-black text-[9px] font-bold tracking-widest uppercase hover:bg-[#ff4b26] hover:text-white disabled:opacity-50">✕</button>
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
    </Modal>
  );
}

/* ── Панель друзей: 2 кнопки ── */
function FriendsPanel({ version, onOpen }: { version: number; onOpen: (m: "search" | "list") => void }) {
  const [incoming, setIncoming] = useState(0);
  const [friendsCount, setFriendsCount] = useState<number | null>(null);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const r = await authApi.get("/api/friends");
        setIncoming(r.data.incoming?.length ?? 0);
        setFriendsCount(r.data.friends?.length ?? 0);
        setLoadError("");
      } catch (error: unknown) {
        setLoadError(getApiErrorMessage(error, "Не удалось загрузить данные о друзьях."));
      }
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
      {loadError && <p role="alert" className="mt-3 text-sm font-bold text-[#a62910]">{loadError}</p>}
      <p className="text-[10px] font-bold tracking-widest uppercase text-[#666] mt-4">
        Friends compete in the Friends rating on your dashboard
      </p>
    </div>
  );
}

type ClubSummary = {
  id: number;
  name: string;
  invite_code?: string | null;
  instant_join?: boolean;
  owner_id?: number;
  is_owner?: boolean;
  is_member?: boolean;
  member_count: number;
  my_role?: string | null;
};

type ClubMember = {
  id: number;
  username: string | null;
  display_name: string;
  level: number | null;
  hidden: boolean;
  role: string;
  can_be_removed: boolean;
};

type ClubJoinRequest = {
  request_id: number;
  club_id: number;
  club_name: string;
  user: { id: number; username: string; display_name: string; level: number };
};

type ClubRankingRow = {
  id: number;
  username: string | null;
  display_name: string;
  level: number | null;
  hidden: boolean;
  score: number | null;
  rank: number | null;
  role: string;
};

type ClubDetail = {
  club: ClubSummary;
  members: ClubMember[];
  rankings: { weekly: ClubRankingRow[]; seasonal: ClubRankingRow[] };
};

type ClubConfirmAction =
  | { kind: "leave"; club: ClubSummary; targetId?: number }
  | { kind: "delete"; club: ClubSummary }
  | { kind: "transfer"; club: ClubSummary; targetId: number }
  | { kind: "kick"; club: ClubSummary; member: ClubMember }
  | null;

function ClubsPanel() {
  const [clubs, setClubs] = useState<ClubSummary[]>([]);
  const [incoming, setIncoming] = useState<ClubJoinRequest[]>([]);
  const [ownedCount, setOwnedCount] = useState(0);
  const [membershipCount, setMembershipCount] = useState(0);
  const [selectedClubId, setSelectedClubId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ClubDetail | null>(null);
  const [detailVersion, setDetailVersion] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [name, setName] = useState("");
  const [instantJoin, setInstantJoin] = useState(false);
  const [code, setCode] = useState("");
  const [joinBusy, setJoinBusy] = useState(false);
  const [searchText, setSearchText] = useState("");
  const [searchResults, setSearchResults] = useState<{
    id: number; name: string; member_count: number; is_member: boolean; has_pending_request: boolean; instant_join: boolean;
  }[]>([]);
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [renameDraft, setRenameDraft] = useState("");
  const [instantJoinDraft, setInstantJoinDraft] = useState(false);
  const [transferTargetId, setTransferTargetId] = useState("");
  const [rankTab, setRankTab] = useState<"weekly" | "seasonal">("weekly");
  const [confirm, setConfirm] = useState<ClubConfirmAction>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const [confirmError, setConfirmError] = useState("");
  const [requestBusyId, setRequestBusyId] = useState<number | null>(null);

  const loadMine = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await authApi.get("/api/clubs/mine");
      const data = response.data;
      setClubs(Array.isArray(data.clubs) ? data.clubs : []);
      setIncoming(Array.isArray(data.incoming_requests) ? data.incoming_requests : []);
      setOwnedCount(typeof data.owned_count === "number" ? data.owned_count : 0);
      setMembershipCount(typeof data.membership_count === "number" ? data.membership_count : 0);
    } catch (loadError: unknown) {
      setError(getApiErrorMessage(loadError, "Не удалось загрузить клубы."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMine();
  }, [loadMine]);

  useEffect(() => {
    if (selectedClubId === null) {
      setDetail(null);
      setDetailError("");
      setDetailLoading(false);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    setDetailError("");
    (async () => {
      try {
        const response = await authApi.get(`/api/clubs/${selectedClubId}`);
        if (!cancelled) setDetail(response.data);
      } catch (loadError: unknown) {
        if (!cancelled) {
          setDetail(null);
          setDetailError(getApiErrorMessage(loadError, "Не удалось загрузить состав и рейтинг клуба."));
        }
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [selectedClubId, detailVersion]);

  useEffect(() => {
    if (!detail) return;
    setRenameDraft(detail.club.name);
    setInstantJoinDraft(Boolean(detail.club.instant_join));
    setTransferTargetId("");
  }, [detail]);

  const refreshAfterAction = async () => {
    await loadMine();
    setDetailVersion((version) => version + 1);
  };

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCreateBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await authApi.post("/api/clubs", {
        name,
        instant_join: instantJoin,
      });
      setMessage(typeof response.data.message === "string" ? response.data.message : "Клуб создан.");
      setName("");
      setSelectedClubId(response.data.club?.id ?? null);
      await loadMine();
    } catch (actionError: unknown) {
      setError(getApiErrorMessage(actionError, "Не удалось создать клуб."));
    } finally {
      setCreateBusy(false);
    }
  };

  const handleJoinCode = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setJoinBusy(true);
    setError("");
    setMessage("");
    try {
      const response = await authApi.post("/api/clubs/join", { code: code.trim().toUpperCase() });
      setMessage(typeof response.data.message === "string" ? response.data.message : "Код принят.");
      setCode("");
      if (response.data.joined && typeof response.data.club?.id === "number") {
        setSelectedClubId(response.data.club.id);
      }
      await loadMine();
      setDetailVersion((version) => version + 1);
    } catch (actionError: unknown) {
      setError(getApiErrorMessage(actionError, "Не удалось вступить по коду."));
    } finally {
      setJoinBusy(false);
    }
  };

  const search = async (event?: FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    if (searchText.trim().length < 2) {
      setSearchError("Для поиска введи минимум 2 символа.");
      return;
    }
    setSearchBusy(true);
    setSearchError("");
    try {
      const response = await authApi.get("/api/clubs/search", { params: { q: searchText.trim() } });
      setSearchResults(Array.isArray(response.data.results) ? response.data.results : []);
    } catch (searchFailure: unknown) {
      setSearchError(getApiErrorMessage(searchFailure, "Не удалось найти клубы."));
    } finally {
      setSearchBusy(false);
    }
  };

  const requestJoin = async (clubId: number) => {
    setBusy(`request-${clubId}`);
    setError("");
    setMessage("");
    try {
      const response = await authApi.post("/api/clubs/request", { club_id: clubId });
      setMessage(typeof response.data.message === "string" ? response.data.message : "Заявка отправлена.");
      if (searchText.trim().length >= 2) {
        const refreshed = await authApi.get("/api/clubs/search", { params: { q: searchText.trim() } });
        setSearchResults(Array.isArray(refreshed.data.results) ? refreshed.data.results : []);
      }
      await loadMine();
    } catch (actionError: unknown) {
      setError(getApiErrorMessage(actionError, "Не удалось отправить заявку."));
    } finally {
      setBusy("");
    }
  };

  const respondJoinRequest = async (requestId: number, accept: boolean) => {
    setRequestBusyId(requestId);
    setError("");
    setMessage("");
    try {
      const response = await authApi.post("/api/clubs/requests/respond", {
        request_id: requestId,
        accept,
      });
      setMessage(typeof response.data.message === "string" ? response.data.message : "Заявка обработана.");
      await refreshAfterAction();
      if (searchText.trim().length >= 2) {
        const result = await authApi.get("/api/clubs/search", { params: { q: searchText.trim() } });
        setSearchResults(Array.isArray(result.data.results) ? result.data.results : []);
      }
    } catch (actionError: unknown) {
      setError(getApiErrorMessage(actionError, "Не удалось обработать заявку."));
    } finally {
      setRequestBusyId(null);
    }
  };

  const saveClubSettings = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!detail) return;
    setBusy("settings");
    setError("");
    setMessage("");
    try {
      const response = await authApi.put(`/api/clubs/${detail.club.id}`, {
        name: renameDraft,
        instant_join: instantJoinDraft,
      });
      setMessage(typeof response.data.message === "string" ? response.data.message : "Настройки сохранены.");
      await refreshAfterAction();
    } catch (actionError: unknown) {
      setError(getApiErrorMessage(actionError, "Не удалось сохранить настройки клуба."));
    } finally {
      setBusy("");
    }
  };

  const copyInviteCode = async (inviteCode: string) => {
    setError("");
    try {
      await navigator.clipboard.writeText(inviteCode);
      setMessage("Код вступления скопирован.");
    } catch {
      setMessage(`Не удалось скопировать автоматически. Код: ${inviteCode}`);
    }
  };

  const actOnConfirm = async () => {
    if (!confirm) return;
    setConfirmBusy(true);
    setConfirmError("");
    setError("");
    setMessage("");
    try {
      if (confirm.kind === "delete") {
        const response = await authApi.delete(`/api/clubs/${confirm.club.id}`);
        setMessage(typeof response.data.message === "string" ? response.data.message : "Клуб удалён.");
        setSelectedClubId(null);
      } else if (confirm.kind === "leave") {
        const response = await authApi.post(`/api/clubs/${confirm.club.id}/leave`,
          confirm.targetId ? { transfer_to_user_id: confirm.targetId } : {});
        setMessage(typeof response.data.message === "string" ? response.data.message : "Ты вышел из клуба.");
        if (selectedClubId === confirm.club.id) setSelectedClubId(null);
      } else if (confirm.kind === "transfer") {
        const response = await authApi.post(`/api/clubs/${confirm.club.id}/transfer-owner`, {
          user_id: confirm.targetId,
        });
        setMessage(typeof response.data.message === "string" ? response.data.message : "Владелец изменён.");
      } else {
        const response = await authApi.post(`/api/clubs/${confirm.club.id}/kick`, {
          user_id: confirm.member.id,
        });
        setMessage(typeof response.data.message === "string" ? response.data.message : "Участник исключён.");
      }
      setConfirm(null);
      await refreshAfterAction();
      if (searchText.trim().length >= 2) {
        const result = await authApi.get("/api/clubs/search", { params: { q: searchText.trim() } });
        setSearchResults(Array.isArray(result.data.results) ? result.data.results : []);
      }
    } catch (actionError: unknown) {
      setConfirmError(getApiErrorMessage(actionError, "Не удалось выполнить действие. Обнови данные и попробуй ещё раз."));
    } finally {
      setConfirmBusy(false);
    }
  };

  const confirmationProps = (() => {
    if (!confirm) return null;
    if (confirm.kind === "delete") return {
      title: "Удалить клуб?",
      text: `Клуб «${confirm.club.name}», его состав и заявки будут удалены без возможности восстановления.`,
      confirmLabel: "Удалить клуб",
    };
    if (confirm.kind === "leave") return {
      title: confirm.targetId ? "Передать клуб и выйти?" : "Выйти из клуба?",
      text: confirm.targetId
        ? `Владение клубом «${confirm.club.name}» перейдёт выбранному участнику, после чего ты покинешь клуб.`
        : `Ты покинешь клуб «${confirm.club.name}». Вернуться можно будет по коду или заявке.`,
      confirmLabel: confirm.targetId ? "Передать и выйти" : "Выйти",
    };
    if (confirm.kind === "transfer") return {
      title: "Передать владельца?",
      text: `Выбранный участник станет владельцем клуба «${confirm.club.name}». Ты останешься участником.`,
      confirmLabel: "Передать владельца",
    };
    return {
      title: "Исключить участника?",
      text: `Участник «${confirm.member.display_name}» будет удалён из клуба «${confirm.club.name}».`,
      confirmLabel: "Исключить",
    };
  })();

  const canCreate = ownedCount < 3 && membershipCount < 10;
  const rankingRows = detail?.rankings?.[rankTab] ?? [];

  return (
    <div className="p-4 md:p-6 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display uppercase text-2xl md:text-3xl">Клубы</h2>
          <p className="mt-1 text-[10px] font-bold tracking-widest uppercase text-[#666]">
            Владение: {ownedCount}/3 · Членство: {membershipCount}/10
          </p>
        </div>
        <button type="button" onClick={() => void loadMine()} disabled={loading} className="border-2 border-black bg-white px-3 py-2 text-[10px] font-bold uppercase tracking-widest hover:bg-[#ffd500] disabled:opacity-50">
          {loading ? "Загружаю…" : "Обновить"}
        </button>
      </div>

      {error && (
        <div role="alert" className="border-2 border-[#ff4b26] bg-[#ff4b26]/10 p-3 text-sm font-bold text-[#a62910]">
          <p>{error}</p>
          <button type="button" onClick={() => void loadMine()} className="mt-2 underline">Повторить загрузку</button>
        </div>
      )}
      {message && <p role="status" className="border-l-4 border-[#16a34a] bg-white px-3 py-2 text-sm font-bold text-[#166534]">{message}</p>}

      <div className="grid lg:grid-cols-2 gap-4">
        <form onSubmit={handleCreate} className="border-2 border-black bg-white p-4 space-y-3">
          <h3 className="font-display uppercase text-xl">Создать клуб</h3>
          <p className="text-xs text-[#666]">Можно владеть максимум тремя клубами и состоять максимум в десяти.</p>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            minLength={2}
            maxLength={40}
            required
            placeholder="Название клуба (2–40 символов)"
            className="w-full border-2 border-black px-3 py-3 text-sm font-bold"
          />
          <label className="flex items-start gap-2 text-sm">
            <input type="checkbox" checked={instantJoin} onChange={(event) => setInstantJoin(event.target.checked)} className="mt-1" />
            <span>Мгновенное вступление по коду. Если выключено — вступление только после одобрения заявки владельцем.</span>
          </label>
          {ownedCount >= 3 && <p className="text-sm font-bold text-[#a62910]">Лимит владения — 3 клуба.</p>}
          {membershipCount >= 10 && <p className="text-sm font-bold text-[#a62910]">Сначала выйди из одного из клубов, чтобы создать новый.</p>}
          <button type="submit" disabled={createBusy || !canCreate} className="w-full border-2 border-black bg-[#ffd500] px-4 py-3 text-[10px] font-bold uppercase tracking-widest hover:bg-black hover:text-white disabled:opacity-50">
            {createBusy ? "Создаю…" : "Создать клуб"}
          </button>
        </form>

        <div className="space-y-4">
          <form onSubmit={handleJoinCode} className="border-2 border-black bg-white p-4 space-y-3">
            <h3 className="font-display uppercase text-xl">Вступить по коду</h3>
            <p className="text-xs text-[#666]">Код состоит из 12 символов Base32.</p>
            <input
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
              minLength={12}
              maxLength={12}
              required
              pattern="[A-Z2-7]{12}"
              placeholder="КОД ВСТУПЛЕНИЯ"
              className="w-full border-2 border-black px-3 py-3 font-mono text-sm uppercase tracking-widest"
            />
            <button type="submit" disabled={joinBusy || code.trim().length !== 12 || membershipCount >= 10} className="w-full border-2 border-black bg-white px-4 py-3 text-[10px] font-bold uppercase tracking-widest hover:bg-[#ffd500] disabled:opacity-50">
              {joinBusy ? "Проверяю…" : "Вступить / отправить заявку"}
            </button>
          </form>

          <form onSubmit={search} className="border-2 border-black bg-white p-4 space-y-3">
            <h3 className="font-display uppercase text-xl">Найти клуб</h3>
            <div className="flex gap-2">
              <input value={searchText} onChange={(event) => setSearchText(event.target.value)} minLength={2} maxLength={40} placeholder="Название клуба" className="min-w-0 flex-1 border-2 border-black px-3 py-2 text-sm" />
              <button type="submit" disabled={searchBusy || searchText.trim().length < 2} className="border-2 border-black bg-[#ffd500] px-3 py-2 text-[10px] font-bold uppercase disabled:opacity-50">
                {searchBusy ? "…" : "Поиск"}
              </button>
            </div>
            {searchError && (
              <div role="alert" className="text-sm font-bold text-[#a62910]">
                <p>{searchError}</p>
                <button type="button" onClick={(event) => { event.preventDefault(); void search(); }} className="underline">Повторить поиск</button>
              </div>
            )}
            {searchResults.length === 0 && !searchBusy && !searchError && (
              <p className="text-xs text-[#777]">{searchText.trim().length >= 2 ? "Клубы не найдены." : "Введи минимум 2 символа для поиска."}</p>
            )}
            {searchResults.map((result) => (
              <div key={result.id} className="flex flex-wrap items-center justify-between gap-2 border-t border-black/15 pt-3">
                <div>
                  <p className="font-bold">{result.name}</p>
                  <p className="text-[10px] text-[#666]">{result.member_count}/30 участников</p>
                </div>
                {result.is_member ? (
                  <span className="text-[10px] font-bold uppercase text-[#166534]">Участник</span>
                ) : result.has_pending_request ? (
                  <span className="text-[10px] font-bold uppercase text-[#666]">Заявка отправлена</span>
                ) : result.instant_join ? (
                  <span className="text-right text-[10px] font-bold uppercase text-[#666]">Нужен код<br />из приглашения</span>
                ) : (
                  <button type="button" onClick={() => void requestJoin(result.id)} disabled={busy === `request-${result.id}` || membershipCount >= 10} className="border-2 border-black bg-white px-3 py-2 text-[10px] font-bold uppercase hover:bg-[#ffd500] disabled:opacity-50">
                    {busy === `request-${result.id}` ? "Отправляю…" : "Подать заявку"}
                  </button>
                )}
              </div>
            ))}
          </form>
        </div>
      </div>

      {incoming.length > 0 && (
        <section className="border-2 border-black bg-white p-4 space-y-3">
          <h3 className="font-display uppercase text-xl">Входящие заявки · {incoming.length}</h3>
          {incoming.map((request) => (
            <div key={request.request_id} className="flex flex-wrap items-center justify-between gap-3 border-t border-black/15 pt-3">
              <div>
                <p className="font-bold">{request.user.display_name} <span className="font-normal text-[#666]">@{request.user.username}</span></p>
                <p className="text-xs text-[#666]">В клуб «{request.club_name}» · уровень {request.user.level}</p>
              </div>
              <div className="flex gap-2">
                <button type="button" disabled={requestBusyId === request.request_id} onClick={() => void respondJoinRequest(request.request_id, true)} className="border-2 border-black bg-[#ffd500] px-3 py-2 text-[10px] font-bold uppercase disabled:opacity-50">Принять</button>
                <button type="button" disabled={requestBusyId === request.request_id} onClick={() => void respondJoinRequest(request.request_id, false)} className="border-2 border-black bg-white px-3 py-2 text-[10px] font-bold uppercase hover:bg-[#ff4b26] hover:text-white disabled:opacity-50">Отклонить</button>
              </div>
            </div>
          ))}
        </section>
      )}

      <section className="space-y-3">
        <h3 className="font-display uppercase text-xl">Мои клубы</h3>
        {loading ? (
          <p className="border-2 border-black bg-white p-4 text-sm text-[#666]">Загружаю клубы…</p>
        ) : clubs.length === 0 ? (
          <div className="border-2 border-dashed border-black/40 bg-white p-6 text-center">
            <p className="font-bold">Ты пока не состоишь ни в одном клубе.</p>
            <p className="mt-1 text-sm text-[#666]">Создай клуб, найди существующий или вступи по приглашению.</p>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 gap-3">
            {clubs.map((club) => (
              <button key={club.id} type="button" onClick={() => setSelectedClubId(club.id)} className={`border-2 border-black p-4 text-left transition-colors ${selectedClubId === club.id ? "bg-[#ffd500]" : "bg-white hover:bg-[#ffd500]/50"}`}>
                <span className="flex items-center justify-between gap-2">
                  <span className="font-display uppercase text-lg">{club.name}</span>
                  {club.is_owner && <span className="text-[9px] font-bold uppercase tracking-widest">Владелец</span>}
                </span>
                <span className="mt-1 block text-[10px] font-bold uppercase tracking-widest text-[#666]">{club.member_count}/30 участников</span>
                {club.invite_code && (
                  <span className="mt-2 block font-mono text-xs tracking-widest">{club.invite_code}</span>
                )}
              </button>
            ))}
          </div>
        )}
      </section>

      {selectedClubId !== null && (
        <section className="border-2 border-black bg-white">
          {detailLoading ? (
            <p className="p-4 text-sm text-[#666]">Загружаю клуб…</p>
          ) : detailError ? (
            <div role="alert" className="p-4 text-sm font-bold text-[#a62910]">
              <p>{detailError}</p>
              <button type="button" onClick={() => setDetailVersion((version) => version + 1)} className="mt-2 underline">Повторить</button>
            </div>
          ) : detail ? (
            <>
              <div className="border-b-2 border-black bg-[#171a38] p-4 text-white">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-display uppercase text-2xl">{detail.club.name}</h3>
                    <p className="mt-1 text-[10px] font-bold uppercase tracking-widest text-white/70">{detail.club.member_count}/30 участников</p>
                  </div>
                  <button type="button" onClick={() => setSelectedClubId(null)} className="border-2 border-white px-3 py-2 text-[10px] font-bold uppercase hover:bg-white hover:text-black">Закрыть</button>
                </div>
                {detail.club.invite_code && (
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <span className="font-mono text-lg tracking-[0.18em]">{detail.club.invite_code}</span>
                    <button type="button" onClick={() => void copyInviteCode(detail.club.invite_code!)} className="border-2 border-white px-3 py-2 text-[10px] font-bold uppercase hover:bg-white hover:text-black">Копировать код</button>
                  </div>
                )}
              </div>

              {detail.club.is_owner && (
                <form onSubmit={saveClubSettings} className="border-b-2 border-black p-4 space-y-3">
                  <h4 className="font-display uppercase text-lg">Настройки клуба</h4>
                  <input value={renameDraft} onChange={(event) => setRenameDraft(event.target.value)} minLength={2} maxLength={40} required className="w-full border-2 border-black px-3 py-2 text-sm font-bold" aria-label="Название клуба" />
                  <label className="flex items-start gap-2 text-sm">
                    <input type="checkbox" checked={instantJoinDraft} onChange={(event) => setInstantJoinDraft(event.target.checked)} className="mt-1" />
                    <span>Разрешить мгновенное вступление по коду без одобрения заявки</span>
                  </label>
                  <button type="submit" disabled={busy === "settings"} className="border-2 border-black bg-[#ffd500] px-4 py-2 text-[10px] font-bold uppercase disabled:opacity-50">
                    {busy === "settings" ? "Сохраняю…" : "Сохранить"}
                  </button>
                </form>
              )}

              <div className="border-b-2 border-black p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <h4 className="font-display uppercase text-lg">Рейтинг</h4>
                  <div className="flex border-2 border-black">
                    <button type="button" onClick={() => setRankTab("weekly")} className={`px-3 py-2 text-[10px] font-bold uppercase ${rankTab === "weekly" ? "bg-[#ffd500]" : "bg-white"}`}>Неделя</button>
                    <button type="button" onClick={() => setRankTab("seasonal")} className={`border-l-2 border-black px-3 py-2 text-[10px] font-bold uppercase ${rankTab === "seasonal" ? "bg-[#ffd500]" : "bg-white"}`}>Сезон</button>
                  </div>
                </div>
                {rankingRows.length === 0 ? (
                  <p className="mt-3 text-sm text-[#666]">Пока нет данных рейтинга.</p>
                ) : (
                  <div className="mt-3 space-y-2">
                    {rankingRows.map((row) => (
                      <div key={row.id} className="grid grid-cols-[2rem_1fr_auto] items-center gap-3 border-t border-black/10 py-2">
                        <span className="font-display text-lg text-[#666]">{row.rank ?? "—"}</span>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-bold">{row.display_name}</p>
                          <p className="text-[9px] font-bold uppercase tracking-widest text-[#777]">{row.hidden ? "Профиль скрыт" : row.username ? `@${row.username}` : row.role}</p>
                        </div>
                        <span className="font-display text-lg">{row.hidden || row.score === null ? "Скрыто" : Math.round(row.score)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="border-b-2 border-black p-4 space-y-3">
                <h4 className="font-display uppercase text-lg">Участники · {detail.members.length}</h4>
                {detail.members.map((member) => (
                  <div key={member.id} className="flex flex-wrap items-center justify-between gap-3 border-t border-black/10 pt-3">
                    <div>
                      <p className="font-bold">{member.display_name} {member.role === "owner" && <span className="text-[9px] uppercase tracking-widest text-[#5866f2]">Владелец</span>}</p>
                      <p className="text-[10px] text-[#666]">{member.hidden ? "Профиль скрыт" : member.username ? `@${member.username}` : ""}</p>
                    </div>
                    {member.can_be_removed && (
                      <button type="button" onClick={() => { setConfirmError(""); setConfirm({ kind: "kick", club: detail.club, member }); }} className="border-2 border-[#ff4b26] px-3 py-2 text-[10px] font-bold uppercase text-[#ff4b26] hover:bg-[#ff4b26] hover:text-white">Исключить</button>
                    )}
                  </div>
                ))}
              </div>

              <div className="p-4 space-y-3">
                {detail.club.is_owner && detail.members.filter((member) => member.id !== detail.club.owner_id).length > 0 && (
                  <div className="border-2 border-black/15 p-3 space-y-2">
                    <label className="block text-[10px] font-bold uppercase tracking-widest text-[#666]">Передать владение</label>
                    <select value={transferTargetId} onChange={(event) => setTransferTargetId(event.target.value)} className="w-full border-2 border-black bg-white px-3 py-2 text-sm">
                      <option value="">Выбери участника</option>
                      {detail.members.filter((member) => member.id !== detail.club.owner_id).map((member) => (
                        <option key={member.id} value={member.id}>{member.hidden ? `Участник #${member.id}` : member.display_name}</option>
                      ))}
                    </select>
                    <button type="button" disabled={!transferTargetId} onClick={() => { setConfirmError(""); setConfirm({ kind: "transfer", club: detail.club, targetId: Number(transferTargetId) }); }} className="border-2 border-black bg-[#ffd500] px-3 py-2 text-[10px] font-bold uppercase disabled:opacity-50">Передать владельца</button>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    disabled={busy === "leave" || (detail.club.is_owner && !transferTargetId)}
                    onClick={() => { setConfirmError(""); setConfirm({ kind: "leave", club: detail.club, targetId: detail.club.is_owner ? Number(transferTargetId) : undefined }); }}
                    className="border-2 border-black bg-white px-4 py-3 text-[10px] font-bold uppercase hover:bg-[#ffd500] disabled:opacity-50"
                  >
                    {detail.club.is_owner ? "Передать и выйти" : "Выйти из клуба"}
                  </button>
                  {detail.club.is_owner && (
                    <button type="button" onClick={() => { setConfirmError(""); setConfirm({ kind: "delete", club: detail.club }); }} className="border-2 border-[#ff4b26] px-4 py-3 text-[10px] font-bold uppercase text-[#ff4b26] hover:bg-[#ff4b26] hover:text-white">Удалить клуб</button>
                  )}
                </div>
                {detail.club.is_owner && !transferTargetId && detail.members.some((member) => member.id !== detail.club.owner_id) && (
                  <p className="text-xs text-[#666]">Чтобы выйти и сохранить клуб, сначала выбери нового владельца. Иначе используй «Удалить клуб».</p>
                )}
              </div>
            </>
          ) : null}
        </section>
      )}

      {confirm && confirmationProps && (
        <ConfirmDialog
          title={confirmationProps.title}
          text={confirmationProps.text}
          confirmLabel={confirmationProps.confirmLabel}
          busy={confirmBusy}
          error={confirmError}
          onClose={() => { if (!confirmBusy) { setConfirm(null); setConfirmError(""); } }}
          onConfirm={actOnConfirm}
        />
      )}
    </div>
  );
}

/* ── Сам контейнер Social ── */
export default function SocialHub() {
  const [tab, setTab] = useState<Tab>("friends");
  const [modal, setModal] = useState<ModalKind>(null);
  const [version, setVersion] = useState(0);
  const [friendRequestError, setFriendRequestError] = useState("");
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

          {tab === "friends" ? <FriendsPanel version={version} onOpen={setModal} /> : <ClubsPanel />}
        </div>
      </div>

      {/* Модалки */}
      <AnimatePresence>
        {modal === "search" && <SearchModal onClose={() => setModal(null)} onChanged={bump} onError={setFriendRequestError} />}
        {modal === "list" && <ListModal onClose={() => setModal(null)} onChanged={bump} />}
      </AnimatePresence>
      <AnimatePresence>
        {friendRequestError && (
          <ConfirmDialog
            title="Ошибка заявки в друзья"
            text={friendRequestError}
            confirmLabel="Понятно"
            danger={false}
            busy={false}
            onClose={() => setFriendRequestError("")}
            onConfirm={() => setFriendRequestError("")}
          />
        )}
      </AnimatePresence>
    </div>
  );
}