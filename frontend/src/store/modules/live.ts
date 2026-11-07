import { defineStore } from "pinia";
import { ElNotification } from "element-plus";
import { http } from "@/utils/http";
let stream: EventSource | undefined;
export const useLiveStore = defineStore("award-live", {
  state: () => ({
    readReceipts: {} as Record<number, string>,
    readingAll: false,
    connected: false,
    notifications: [] as any[],
    jobs: [] as any[],
    files: [] as any[],
    unread: 0,
    pending: 0,
    revision: "",
    initialized: false
  }),
  actions: {
    start() {
      if (stream) return;
      stream = new EventSource("/api/v1/events/");
      stream.addEventListener("state", (event: MessageEvent) => {
        const data = JSON.parse(event.data),
          known = new Set(this.notifications.map(n => n.id));
        if (this.initialized)
          for (const notice of data.notifications)
            if (!known.has(notice.id) && !notice.read_at)
              ElNotification({
                title: notice.title,
                message: notice.body,
                type: notice.kind === "failed" ? "error" : "info",
                duration: 6500,
                onClick: () =>
                  window.dispatchEvent(
                    new CustomEvent("award-notification", { detail: notice })
                  )
              });
        let staleReads = 0;
        for (const notice of data.notifications)
          if (!notice.read_at && this.readReceipts[notice.id]) {
            notice.read_at = this.readReceipts[notice.id];
            staleReads++;
          }
        data.unread = Math.max(0, data.unread - staleReads);
        Object.assign(this, data, { connected: true, initialized: true });
      });
      stream.onerror = () => (this.connected = false);
      stream.addEventListener("session-expired", () => {
        this.stop();
        window.dispatchEvent(new Event("award-session-expired"));
        ElNotification({
          title: "登录状态已失效",
          message: "请重新登录以继续接收通知",
          type: "warning",
          duration: 0,
          onClick: () => location.reload()
        });
      });
    },
    stop() {
      stream?.close();
      stream = undefined;
      this.$reset();
    },
    async read(id: number) {
      const result = await http.request<any>(
        "patch",
        `/api/v1/notifications/${id}/`,
        { data: { read_at: true } }
      );
      const readAt = result.read_at || new Date().toISOString();
      this.readReceipts[id] = readAt;
      const notice = this.notifications.find(n => n.id === id);
      if (notice) notice.read_at = readAt;
      this.unread = result.unreadCount;
    },
    async readAll() {
      if (this.readingAll) return;
      this.readingAll = true;
      const ids = this.notifications.map(n => n.id);
      try {
        const result = await http.post<any, object>(
          "/api/v1/notifications/read_all/",
          { data: {} }
        );
        for (const id of ids) {
          this.readReceipts[id] = new Date().toISOString();
          const notice = this.notifications.find(n => n.id === id);
          if (notice) notice.read_at = this.readReceipts[id];
        }
        this.unread = result.unreadCount;
      } finally {
        this.readingAll = false;
      }
    },
    badge(path: string) {
      if (path.endsWith("/approvals")) return this.pending;
      if (path.endsWith("/batches"))
        return (
          this.jobs.filter(j => ["queued", "running"].includes(j.status))
            .length +
          this.notifications.filter(
            n => !n.read_at && n.target?.startsWith("/business/batches")
          ).length
        );
      return 0;
    }
  }
});
