import type { Router } from "vue-router";
import { ElMessageBox } from "element-plus";
import { useLiveStore } from "@/store/modules/live";
export function notificationTarget(notice: any) {
  const target = String(notice.target || "");
  if (/^\/business\/(approvals|batches|certificates|logs)(\?|$)/.test(target))
    return target;
  if (/审批|会签/.test(notice.title)) return "/business/approvals";
  if (/签发|生成|退回/.test(notice.title)) return "/business/batches";
  if (/作废/.test(notice.title)) return "/business/certificates";
  return "";
}
export function openNotification(router: Router, notice: any) {
  // A failed read receipt must never prevent business navigation.
  if (!notice.read_at)
    void useLiveStore()
      .read(notice.id)
      .catch(() => {});
  const target = notificationTarget(notice);
  if (target)
    void router.push({
      path: target.split("?")[0],
      query: {
        ...Object.fromEntries(new URLSearchParams(target.split("?")[1] || "")),
        notice: String(notice.id)
      }
    });
  else void ElMessageBox.alert(notice.body, notice.title);
}
