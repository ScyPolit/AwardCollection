import { computed, onMounted, ref } from "vue";
import { currentUser } from "@/api/business";
import { useUserStoreHook } from "@/store/modules/user";
const user = ref({
  username: "",
  isSuperuser: false,
  roles: [] as string[],
  managedDepartmentIds: [] as number[]
});
let pending: Promise<void> | undefined,
  loadedAt = 0;
export async function ensureBusinessAccess() {
  const store = useUserStoreHook();
  if (user.value.username !== store.username) {
    user.value = {
      username: store.username,
      isSuperuser: store.roles.includes("super"),
      roles: store.roles,
      managedDepartmentIds: []
    };
    loadedAt = 0;
    pending = undefined;
  }
  if (Date.now() - loadedAt < 30000) return;
  if (!pending)
    pending = currentUser()
      .then(value => {
        user.value = value;
        loadedAt = Date.now();
      })
      .finally(() => (pending = undefined));
  return pending;
}
export function useBusinessAccess() {
  const store = useUserStoreHook();
  if (user.value.username !== store.username) {
    user.value = {
      username: store.username,
      isSuperuser: store.roles.includes("super"),
      roles: store.roles,
      managedDepartmentIds: []
    };
    loadedAt = 0;
    pending = undefined;
  }
  onMounted(() => ensureBusinessAccess().catch(() => {}));
  const isSuper = computed(() => user.value.isSuperuser);
  const isAdmin = computed(
    () => isSuper.value || user.value.roles.includes("admin")
  );
  return { user, isSuper, isAdmin };
}
