import { ref, onBeforeUnmount } from "vue";
import { http } from "@/utils/http";
export type PreparedFile = {
  id: string;
  status: string;
  processed: number;
  total: number;
  percent: number;
  bytes: number;
  download_url?: string;
  error?: string;
};

export function usePreparedFile() {
  const file = ref<PreparedFile>(),
    loading = ref(false),
    error = ref("");
  let timer: ReturnType<typeof setTimeout> | undefined,
    epoch = 0;
  function stop() {
    ++epoch;
    clearTimeout(timer);
  }
  async function start(data: Record<string, unknown>) {
    stop();
    const current = epoch;
    loading.value = true;
    error.value = "";
    file.value = undefined;
    try {
      const value = await http.post<PreparedFile, object>(
        "/api/v1/prepared-files/",
        { data }
      );
      if (current !== epoch) return;
      file.value = value;
      if (!["ready", "failed"].includes(value.status))
        timer = setTimeout(() => poll(value.id, current), 1800);
    } catch (reason: any) {
      if (current === epoch)
        error.value = reason?.response?.data?.detail || "准备失败，请重试";
    } finally {
      if (current === epoch) loading.value = false;
    }
  }
  async function poll(id: string, current: number) {
    if (current !== epoch) return;
    if (document.hidden) {
      timer = setTimeout(() => poll(id, current), 3000);
      return;
    }
    try {
      const value = await http.get<PreparedFile, never>(
        `/api/v1/prepared-files/${id}/`
      );
      if (current !== epoch) return;
      file.value = value;
      if (!["ready", "failed"].includes(value.status))
        timer = setTimeout(() => poll(id, current), 1800);
    } catch (reason: any) {
      if (current === epoch)
        error.value = reason?.response?.data?.detail || "连接中断，请重试";
    }
  }
  onBeforeUnmount(stop);
  return { file, loading, error, start, stop };
}
