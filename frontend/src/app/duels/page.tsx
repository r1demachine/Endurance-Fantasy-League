import { redirect } from "next/navigation";

export default function DuelsRedirect() {
  redirect("/compete?tab=duels");
}
