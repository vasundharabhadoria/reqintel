// Where a signed-in user lands by default.
export function homePathForUser(user) {
  return user?.role === "admin" ? "/master-module" : "/dashboard";
}
