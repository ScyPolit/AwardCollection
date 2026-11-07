import { ref, onBeforeUnmount } from "vue";

/** Local request feedback. An older response can never replace a newer selection. */
export function useModuleTask() {
  const loading = ref(false),
    error = ref("");
  let revision = 0;
  onBeforeUnmount(() => ++revision);
  async function run<T>(request: () => Promise<T>, apply?: (value: T) => void) {
    const current = ++revision;
    loading.value = true;
    error.value = "";
    try {
      const value = await request();
      if (current === revision) apply?.(value);
      return value;
    } catch (reason: any) {
      if (current === revision)
        error.value = reason?.response?.data?.detail || "加载失败，请重试";
      throw reason;
    } finally {
      if (current === revision) loading.value = false;
    }
  }
  return { loading, error, run };
}
