import { computed, onMounted, ref } from "vue";
import { currentUser } from "@/api/business";

export function useBusinessAccess() {
  const user = ref({
    username: "",
    isSuperuser: false,
    roles: [] as string[],
    managedDepartmentIds: [] as number[]
  });
  onMounted(async () => {
    user.value = await currentUser();
  });
  const isSuper = computed(() => user.value.isSuperuser);
  const isAdmin = computed(
    () => isSuper.value || user.value.roles.includes("admin")
  );
  return { user, isSuper, isAdmin };
}
