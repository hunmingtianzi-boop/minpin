import {
  Avatar,
  Button,
  DrawerBody,
  DrawerHeader,
  DrawerHeaderTitle,
  OverlayDrawer,
  Tooltip,
} from "@fluentui/react-components";
import {
  Alert24Regular,
  Book24Regular,
  Box24Regular,
  Briefcase24Regular,
  Building24Regular,
  Chat24Regular,
  ContactCardGroup24Regular,
  Dismiss24Regular,
  ArrowDownload24Regular,
  Eye24Regular,
  Home24Regular,
  Lightbulb24Regular,
  Navigation24Regular,
  PeopleTeam24Regular,
  PeopleSettings24Regular,
  ShieldLock24Regular,
  ShieldError24Regular,
  SignOut24Regular,
} from "@fluentui/react-icons";
import { useState } from "react";
import type { ComponentType, ReactNode } from "react";

import { useAuth } from "../auth/AuthContext";
import { hasPermission } from "../auth/permissions";
import type { AdminUser } from "../api/types";
import {
  APP_PATHS,
  onInternalLinkClick,
  type AppPath,
  usePathname,
} from "../routing";

type NavItem = {
  path: AppPath;
  label: string;
  icon: ComponentType;
  permission?: string;
  allowCardOwner?: boolean;
  role?: string;
};

const navGroups: Array<{ label: string; items: NavItem[] }> = [
  {
    label: "工作台",
    items: [{ path: APP_PATHS.overview, label: "业务概览", icon: Home24Regular }],
  },
  {
    label: "客户旅程",
    items: [
      { path: APP_PATHS.visits, label: "访问记录", icon: Eye24Regular, permission: "visits.read", allowCardOwner: true },
      { path: APP_PATHS.visitorProfiles, label: "访客画像", icon: PeopleTeam24Regular, permission: "visits.read", allowCardOwner: true },
      { path: APP_PATHS.conversations, label: "AI 对话", icon: Chat24Regular, permission: "conversations.read", allowCardOwner: true },
      { path: APP_PATHS.leads, label: "销售线索", icon: PeopleTeam24Regular, permission: "leads.read", allowCardOwner: true },
      { path: APP_PATHS.exports, label: "数据导出", icon: ArrowDownload24Regular, permission: "exports.read", allowCardOwner: true },
    ],
  },
  {
    label: "知识运营",
    items: [
      { path: APP_PATHS.knowledgeGaps, label: "知识缺口", icon: Lightbulb24Regular, permission: "knowledge.read", allowCardOwner: true },
      { path: APP_PATHS.notifications, label: "通知中心", icon: Alert24Regular },
      { path: APP_PATHS.knowledge, label: "知识 FAQ", icon: Book24Regular, permission: "knowledge.read" },
      { path: APP_PATHS.forbiddenTopics, label: "禁答主题", icon: ShieldError24Regular, permission: "forbidden_topic.read" },
    ],
  },
  {
    label: "内容资产",
    items: [
      { path: APP_PATHS.cards, label: "名片管理", icon: ContactCardGroup24Regular, permission: "card.read" },
      { path: APP_PATHS.products, label: "产品管理", icon: Box24Regular, permission: "catalog.read" },
      { path: APP_PATHS.cases, label: "案例管理", icon: Briefcase24Regular, permission: "catalog.read" },
    ],
  },
  {
    label: "平台治理",
    items: [
      {
        path: APP_PATHS.platformEnterprises,
        label: "企业开通",
        icon: Building24Regular,
        permission: "platform.enterprise.manage",
        role: "platform_admin",
      },
    ],
  },
  {
    label: "企业治理",
    items: [
      { path: APP_PATHS.members, label: "企业用户", icon: PeopleSettings24Regular, permission: "members.manage" },
      { path: APP_PATHS.company, label: "企业资料", icon: Building24Regular, permission: "company.read" },
      { path: APP_PATHS.privacyRequests, label: "隐私请求", icon: ShieldLock24Regular, permission: "privacy.manage" },
    ],
  },
];

export function hasNavPermission(
  user: AdminUser | undefined,
  permission?: string,
  allowCardOwner = false,
): boolean {
  return hasPermission(user, permission, { allowCardOwner });
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const auth = useAuth();
  return (
    <nav className="primary-nav" aria-label="管理工作台主导航">
      {navGroups.map((group) => {
        const visibleItems = group.items.filter(
          (item) =>
            (!item.role || auth.user?.role === item.role) &&
            hasNavPermission(auth.user, item.permission, item.allowCardOwner),
        );
        if (visibleItems.length === 0) return null;
        return (
          <div className="nav-group" key={group.label}>
            <span className="nav-group-label">{group.label}</span>
            {visibleItems.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.path;
              return (
                <a
                  key={item.path}
                  href={item.path}
                  className={active ? "nav-link active" : "nav-link"}
                  aria-current={active ? "page" : undefined}
                  onClick={(event) => {
                    onInternalLinkClick(event, item.path);
                    onNavigate?.();
                  }}
                >
                  <Icon />
                  <span>{item.label}</span>
                </a>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <div className="shell-brand">
      <span className="shell-brand-mark" aria-hidden>
        CF
      </span>
      <div>
        <strong>企业管理</strong>
        <span>数智名片工作台</span>
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="app-shell">
      <aside className="shell-sidebar">
        <Brand />
        <Navigation />
        <div className="sidebar-footer">
          <span>已登录</span>
          <strong>{auth.user?.displayName}</strong>
        </div>
      </aside>

      <div className="shell-workspace">
        <header className="shell-topbar">
          <Button
            className="mobile-menu-button"
            appearance="subtle"
            icon={<Navigation24Regular />}
            aria-label="打开导航"
            onClick={() => setMobileOpen(true)}
          />
          <div className="mobile-brand">企业管理</div>
          <div className="topbar-user">
            <Avatar
              name={auth.user?.displayName || "管理员"}
              size={28}
              color="brand"
              shape="square"
            />
            <div className="topbar-user-copy">
              <strong>{auth.user?.displayName}</strong>
              <span>{auth.user?.role || "企业账号"}</span>
            </div>
            <Tooltip content="退出登录" relationship="label">
              <Button
                appearance="subtle"
                icon={<SignOut24Regular />}
                aria-label="退出登录"
                onClick={() => void auth.logout()}
              />
            </Tooltip>
          </div>
        </header>
        <div className="shell-content">{children}</div>
      </div>

      <OverlayDrawer
        position="start"
        open={mobileOpen}
        onOpenChange={(_, data) => setMobileOpen(data.open)}
        className="mobile-drawer"
      >
        <DrawerHeader>
          <DrawerHeaderTitle
            action={
              <Button
                appearance="subtle"
                icon={<Dismiss24Regular />}
                aria-label="关闭导航"
                onClick={() => setMobileOpen(false)}
              />
            }
          >
            <Brand />
          </DrawerHeaderTitle>
        </DrawerHeader>
        <DrawerBody>
          <Navigation onNavigate={() => setMobileOpen(false)} />
        </DrawerBody>
      </OverlayDrawer>
    </div>
  );
}
