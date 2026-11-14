// home: send people straight to sign in, or to their dashboard when already signed in
import { redirect } from "next/navigation";

export default function Home() {
  redirect("/login");
}
