import { redirect } from "next/navigation";

// Goal ideas now live on the Goals page, as its second tab.
export default function Page() {
  redirect("/goals?tab=ideas");
}
