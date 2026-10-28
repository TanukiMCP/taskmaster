// Session storage behind a small key-value interface: Netlify Blobs in production,
// a Map in tests.

import { upgrade, type Session } from "./engine.ts";

export interface KeyValue {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  delete(key: string): Promise<void>;
  keys(prefix: string): Promise<string[]>;
}

export class MemoryKeyValue implements KeyValue {
  private data = new Map<string, string>();
  async get(key: string) {
    return this.data.get(key) ?? null;
  }
  async set(key: string, value: string) {
    this.data.set(key, value);
  }
  async delete(key: string) {
    this.data.delete(key);
  }
  async keys(prefix: string) {
    return [...this.data.keys()].filter((k) => k.startsWith(prefix));
  }
}

export class Store {
  private kv: KeyValue;

  constructor(kv: KeyValue) {
    this.kv = kv;
  }

  async save(session: Session): Promise<void> {
    await this.kv.set(`sessions/${session.id}`, JSON.stringify(session));
  }

  async load(id: string): Promise<Session | null> {
    const raw = await this.kv.get(`sessions/${id}`);
    return raw ? upgrade(JSON.parse(raw) as Session) : null;
  }

  async recent(limit = 10): Promise<Session[]> {
    const sessions: Session[] = [];
    for (const key of await this.kv.keys("sessions/")) {
      const raw = await this.kv.get(key);
      if (raw) sessions.push(upgrade(JSON.parse(raw) as Session));
    }
    return sessions.sort((a, b) => b.updated.localeCompare(a.updated)).slice(0, limit);
  }
}
