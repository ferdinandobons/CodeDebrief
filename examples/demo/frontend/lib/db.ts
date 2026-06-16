import { UserStatus } from "./userStatus";

export interface User {
  id: string;
  status: UserStatus;
}

export interface Order {
  id: string;
  state: "open" | "paid" | "closed";
}

interface Table<T> {
  find(request: Request): Promise<T>;
}

export const database: {
  users: Table<User>;
  orders: Table<Order>;
} = {
  users: { find: async () => ({ id: "1", status: UserStatus.ACTIVE }) },
  orders: { find: async () => ({ id: "1", state: "open" }) },
};
