import { redirect } from "next/navigation";

// There are no per-"AI employee" pages any more: the Team page shows each team's goals and its
// Reviewer. Old links land there.
export default function Page() {
  redirect("/team");
}
