//! Claude App channel navigation, distinct from working-directory projects.
use super::*;

#[derive(Clone, Default, Deserialize)]
#[serde(default)]
pub(super) struct Project {
    pub product: String,
    pub channel_id: String,
    pub view: String,
    pub thread_root_id: String,
    pub status: String,
    pub reply_count: Option<u64>,
    pub project_label: Label,
    pub thread_label: Label,
    pub messages: Vec<Message>,
}

#[derive(Clone, Default, Deserialize)]
#[serde(default)]
pub(super) struct Label {
    pub title: String,
    pub source: String,
}

#[derive(Default)]
pub(super) struct Reader {
    pub key: Option<(String, String, String)>,
    pub cards: Vec<MessageCard>,
    pub cache: CommonMarkCache,
    focus: Option<usize>,
    scroll: Option<usize>,
    query: String,
    expanded: bool,
}

fn split_width(width: f32, expanded: bool) -> Option<f32> {
    (width >= 700.0 && !expanded).then(|| (width * 0.44).clamp(310.0, width - 360.0))
}

impl VaultApp {
    pub(super) fn claude_project_reader(
        &mut self,
        ui: &mut egui::Ui,
        ctx: &egui::Context,
        selected: usize,
    ) {
        let s = &self.catalog.sessions[selected];
        let title = s.meta.project.clone();
        let main = main(&self.catalog, selected);
        let discussion = is_thread(s);
        ui.horizontal_wrapped(|ui| {
            ui.add(egui::Label::new(RichText::new(&title).size(21.0).strong()).truncate())
                .on_hover_text(&title);
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ui.menu_button("更多", |ui| {
                    if ui.button("复制当前对话").clicked() {
                        ctx.copy_text(self.catalog.sessions[selected].markdown.clone());
                        ui.close_menu();
                    }
                    if ui.button("附件与活动").clicked() {
                        self.show_resources = true;
                        ui.close_menu();
                    }
                    if ui.button("定位会话文件").clicked() {
                        reveal(&self.catalog.sessions[selected].path);
                        ui.close_menu();
                    }
                    let project = self.catalog.sessions[selected].meta.claude_project.as_ref();
                    if let Some(project) = project {
                        ui.separator();
                        ui.label(RichText::new(&project.channel_id).small().color(MUTED));
                        if !project.project_label.title.is_empty() {
                            ui.label(
                                RichText::new("项目名称来自本地保存的导航记录")
                                    .small()
                                    .color(MUTED),
                            )
                            .on_hover_text(&project.project_label.source);
                        }
                        if !project.thread_label.title.is_empty() {
                            ui.label(
                                RichText::new(
                                    if project.thread_label.source == "thread-starting" {
                                        "讨论串标题来自本地缓存的启动事件"
                                    } else {
                                        "讨论串标题来自本地保存的导航记录"
                                    },
                                )
                                .small()
                                .color(MUTED),
                            )
                            .on_hover_text(&project.thread_label.source);
                        }
                    }
                });
                if ui
                    .selectable_label(self.prefs.timeline_view, "项目时间线")
                    .clicked()
                {
                    self.prefs.timeline_view = true;
                    self.save_preferences();
                }
                if ui
                    .selectable_label(self.prefs.text_only, "仅文字")
                    .clicked()
                {
                    self.prefs.text_only = !self.prefs.text_only;
                    self.render_selected(ctx);
                    self.save_preferences();
                }
            });
        });
        ui.label(
            RichText::new("Claude App · Projects · 本地已保存内容")
                .small()
                .color(MUTED),
        )
        .on_hover_text(
            "本地缓存可能不完整；状态为最后观察值，附件保留已有引用。不会连接 Claude 账号。",
        );
        ui.add_space(8.0);
        ui.separator();
        if self.prefs.timeline_view {
            return;
        }
        let width = split_width(ui.available_width(), self.project_reader.expanded);
        let mut action = None;
        if let Some(width) = width {
            egui::SidePanel::right("claude-discussion-pane")
                .resizable(true)
                .default_width(width)
                .min_width(310.0)
                .max_width(ui.available_width() - 360.0)
                .frame(
                    egui::Frame::new()
                        .fill(Color32::WHITE)
                        .inner_margin(egui::Margin {
                            left: 18,
                            right: 0,
                            top: 10,
                            bottom: 0,
                        }),
                )
                .show_inside(ui, |ui| {
                    action = self.claude_discussion_pane(ui, selected, discussion);
                });
            action = self.claude_main_pane(ui, selected, main).or(action);
        } else if discussion {
            action = self.claude_discussion_pane(ui, selected, true);
        } else {
            if let Some(jump) = navigation(ui, &self.catalog, selected) {
                action = Some(ReaderAction::Project(jump));
            }
            action = self.claude_main_pane(ui, selected, main).or(action);
        }
        match action {
            Some(ReaderAction::Image(image)) => {
                self.preview_image = Some(image);
                self.preview_zoom = None;
            }
            Some(ReaderAction::Project(jump)) => {
                // The overview remains visible when opening a discussion. Locate
                // its root there independently of the discussion's own scroll.
                if let Some(main) = main {
                    let root = self.catalog.sessions[jump.session]
                        .meta
                        .claude_project
                        .as_ref()
                        .map(|p| p.thread_root_id.as_str())
                        .unwrap_or("");
                    let position = self.catalog.sessions[main]
                        .meta
                        .claude_project
                        .as_ref()
                        .and_then(|p| p.messages.iter().position(|m| m.id == root));
                    self.project_reader.focus = position;
                    self.project_reader.scroll = position;
                }
                self.open_project(ctx, jump);
            }
            None => {}
        }
    }

    fn claude_main_pane(
        &mut self,
        ui: &mut egui::Ui,
        selected: usize,
        main: Option<usize>,
    ) -> Option<ReaderAction> {
        let Some(main) = main else {
            ui.label("主对话没有本地正文，已保存的讨论串仍可阅读。");
            return None;
        };
        ui.add_space(10.0);
        ui.label(RichText::new("主对话").strong().color(MUTED));
        ui.push_id(
            ("claude-overview", &self.catalog.sessions[main].meta.id),
            |ui| {
                if main == selected {
                    show_message_cards(
                        ui,
                        &mut self.cards,
                        &mut self.cache,
                        self.prefs.thumbnail_width,
                        self.focus_message,
                        &mut self.scroll_target,
                    )
                } else {
                    show_message_cards(
                        ui,
                        &mut self.project_reader.cards,
                        &mut self.project_reader.cache,
                        self.prefs.thumbnail_width,
                        self.project_reader.focus,
                        &mut self.project_reader.scroll,
                    )
                }
            },
        )
        .inner
    }

    fn claude_discussion_pane(
        &mut self,
        ui: &mut egui::Ui,
        selected: usize,
        discussion: bool,
    ) -> Option<ReaderAction> {
        let mut action = None;
        if discussion {
            ui.horizontal(|ui| {
                ui.label(RichText::new("讨论串").strong());
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui
                        .button("×")
                        .on_hover_text("关闭讨论串，返回主对话")
                        .clicked()
                    {
                        action = main(&self.catalog, selected).map(|session| {
                            ReaderAction::Project(Jump {
                                session,
                                message: None,
                            })
                        });
                        self.project_reader.expanded = false;
                    }
                    if ui
                        .button(if self.project_reader.expanded {
                            "收起"
                        } else {
                            "展开"
                        })
                        .on_hover_text("切换讨论串的整栏阅读")
                        .clicked()
                    {
                        self.project_reader.expanded = !self.project_reader.expanded;
                    }
                });
            });
            let s = &self.catalog.sessions[selected];
            ui.add(
                egui::Label::new(RichText::new(&s.display_title).size(16.0).strong()).truncate(),
            )
            .on_hover_text(&s.display_title);
            if let Some(project) = &s.meta.claude_project {
                ui.label(
                    RichText::new(format!(
                        "{} · 已保存 {} 条消息",
                        status(&project.status),
                        s.meta.messages
                    ))
                    .small()
                    .color(MUTED),
                )
                .on_hover_text(project.reply_count.map_or_else(
                    || "来源未提供回复总数".to_string(),
                    |count| format!("来源最后记录 {count} 条回复；本地缓存可能不完整"),
                ));
            }
            if let Some(jump) = navigation(ui, &self.catalog, selected) {
                action = Some(ReaderAction::Project(jump));
            }
            ui.separator();
            let read = ui
                .push_id(("claude-thread", &s.meta.id), |ui| {
                    show_message_cards(
                        ui,
                        &mut self.cards,
                        &mut self.cache,
                        self.prefs.thumbnail_width,
                        self.focus_message,
                        &mut self.scroll_target,
                    )
                })
                .inner;
            read.or(action)
        } else {
            let threads: Vec<_> = related(&self.catalog, selected)
                .into_iter()
                .filter(|&i| is_thread(&self.catalog.sessions[i]))
                .collect();
            ui.label(RichText::new(format!("讨论串 · {}", threads.len())).strong());
            ui.add_space(8.0);
            ui.add(
                egui::TextEdit::singleline(&mut self.project_reader.query)
                    .hint_text("查找讨论串…")
                    .desired_width(f32::INFINITY),
            );
            ui.add_space(8.0);
            let query = self.project_reader.query.trim().to_lowercase();
            egui::ScrollArea::vertical()
                .id_salt((
                    "claude-thread-list",
                    project_identity(&self.catalog.sessions[selected]),
                ))
                .auto_shrink([false, false])
                .show(ui, |ui| {
                    let mut count = 0;
                    for i in threads {
                        let thread = &self.catalog.sessions[i];
                        if !query.is_empty()
                            && !thread.display_title.to_lowercase().contains(&query)
                        {
                            continue;
                        }
                        count += 1;
                        if session_button(ui, thread, false, true) {
                            action = Some(ReaderAction::Project(Jump {
                                session: i,
                                message: None,
                            }));
                        }
                    }
                    if count == 0 {
                        ui.label(RichText::new("没有匹配的讨论串").color(MUTED));
                    }
                });
            action
        }
    }
}

#[derive(Clone, Default, Deserialize)]
#[serde(default)]
pub(super) struct Message {
    pub id: String,
    pub thread_root_id: String,
    pub timestamp: String,
    pub role: String,
    pub has_thread: bool,
    pub linked_thread_ids: Vec<String>,
}

pub(super) struct Link {
    pub label: String,
    pub hint: String,
    pub target: Option<Jump>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub(super) struct Jump {
    pub session: usize,
    pub message: Option<usize>,
}

pub(super) fn is_project(s: &Session) -> bool {
    s.meta.tool == "claude-desktop" && s.meta.source == "code-projects-cache"
}

pub(super) fn is_main(s: &Session) -> bool {
    is_project(s)
        && s.meta
            .claude_project
            .as_ref()
            .is_some_and(|p| p.view == "main")
}

pub(super) fn is_timeline_item(s: &Session) -> bool {
    is_project(s)
        && s.meta
            .claude_project
            .as_ref()
            .is_some_and(|p| p.view == "timeline_item")
}

fn is_thread(s: &Session) -> bool {
    is_project(s) && !is_main(s) && !is_timeline_item(s)
}

pub(super) fn status(value: &str) -> &str {
    match value {
        "working" => "处理中",
        "idle" => "空闲",
        "needs_input" => "等待输入",
        "resolved" => "已解决",
        _ => "状态未知",
    }
}

pub(super) fn hydrate_legacy(root: &Path, branch: &str, meta: &mut SessionMeta) {
    if meta.source != "code-projects-cache" || meta.claude_project.is_some() {
        return;
    }
    let path = root
        .join("records")
        .join(branch)
        .join(&meta.id)
        .join("manifest.json");
    let Some(path) = path.canonicalize().ok().filter(|p| p.starts_with(root)) else {
        return;
    };
    if !fs::metadata(&path).is_ok_and(|s| s.len() <= 16 * 1024 * 1024) {
        return;
    }
    let Some(value) = fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok())
    else {
        return;
    };
    let origin = &value["metadata"]["origin_metadata"];
    let Some(channel) = origin["channel_id"].as_str() else {
        return;
    };
    let thread = origin["thread_root_id"].as_str().unwrap_or("");
    meta.claude_project = Some(Project {
        product: origin["product"].as_str().unwrap_or("").into(),
        channel_id: channel.into(),
        view: if thread.is_empty() { "main" } else { "thread" }.into(),
        thread_root_id: thread.into(),
        ..Default::default()
    });
}

fn related(catalog: &Catalog, selected: usize) -> Vec<usize> {
    let key = project_identity(&catalog.sessions[selected]);
    catalog
        .sessions
        .iter()
        .enumerate()
        .filter_map(|(i, s)| (project_identity(s) == key).then_some(i))
        .collect()
}

pub(super) fn main(catalog: &Catalog, selected: usize) -> Option<usize> {
    related(catalog, selected)
        .into_iter()
        .find(|&i| is_main(&catalog.sessions[i]))
}

pub(super) fn recent(catalog: &Catalog, visible: &[usize]) -> Vec<usize> {
    let mut seen = BTreeSet::new();
    visible
        .iter()
        .copied()
        .filter(|&i| {
            !is_project(&catalog.sessions[i]) || seen.insert(project_identity(&catalog.sessions[i]))
        })
        .collect()
}

pub(super) fn channel_button(
    ui: &mut egui::Ui,
    catalog: &Catalog,
    index: usize,
    selected: Option<usize>,
) -> bool {
    let s = &catalog.sessions[index];
    let rows = related(catalog, index);
    let count = rows
        .iter()
        .filter(|&&i| is_thread(&catalog.sessions[i]))
        .count();
    let (rect, response) = ui.allocate_exact_size(
        egui::vec2(ui.available_width(), SESSION_ROW_HEIGHT),
        egui::Sense::click(),
    );
    let active = selected.is_some_and(|i| rows.contains(&i));
    let name = format!("{} · {count} 个讨论串", s.meta.project);
    response.widget_info(|| {
        egui::WidgetInfo::selected(
            egui::WidgetType::SelectableLabel,
            ui.is_enabled(),
            active,
            &name,
        )
    });
    ui.painter().rect_filled(
        rect,
        7.0,
        if active {
            SELECTED
        } else if response.hovered() {
            HOVER
        } else {
            Color32::TRANSPARENT
        },
    );
    for (text, y, size, color) in [
        (s.meta.project.clone(), 7.0, 13.0, INK),
        (
            format!("Claude App · Projects · {count} 个讨论串"),
            29.0,
            11.0,
            MUTED,
        ),
    ] {
        let mut job = egui::text::LayoutJob::simple(
            text,
            egui::FontId::proportional(size),
            color,
            (rect.width() - 20.0).max(10.0),
        );
        job.wrap.max_rows = 1;
        ui.painter().galley(
            rect.min + egui::vec2(10.0, y),
            ui.painter().layout_job(job),
            color,
        );
    }
    response
        .on_hover_text(format!("{name}\n打开主对话，讨论串在右侧独立显示"))
        .clicked()
}

pub(super) fn group(
    ui: &mut egui::Ui,
    catalog: &Catalog,
    rows: &[usize],
    selected: Option<usize>,
) -> Option<usize> {
    let index = rows[0];
    channel_button(ui, catalog, index, selected).then(|| main(catalog, index).unwrap_or(index))
}

pub(super) fn navigation(ui: &mut egui::Ui, catalog: &Catalog, selected: usize) -> Option<Jump> {
    let s = &catalog.sessions[selected];
    if !is_project(s) {
        return None;
    }
    let mut jump = None;
    ui.horizontal_wrapped(|ui| {
        if is_main(s) {
            ui.label(RichText::new("PROJECTS").size(11.0).color(ACCENT).strong());
            ui.label(RichText::new("主对话").small().strong());
            let threads: Vec<_> = related(catalog, selected)
                .into_iter()
                .filter(|&i| is_thread(&catalog.sessions[i]))
                .collect();
            ui.menu_button(format!("讨论串 · {}", threads.len()), |ui| {
                egui::ScrollArea::vertical()
                    .max_height(360.0)
                    .show(ui, |ui| {
                        for i in threads {
                            if session_button(ui, &catalog.sessions[i], false, true) {
                                jump = Some(Jump {
                                    session: i,
                                    message: None,
                                });
                                ui.close_menu();
                            }
                        }
                    });
            });
        } else {
            let target = main(catalog, selected);
            if ui
                .add_enabled(target.is_some(), egui::Button::new("← 主对话").frame(false))
                .on_hover_text("返回主对话的根消息；没有缓存根消息时返回主对话开头")
                .clicked()
            {
                if let Some(i) = target {
                    let root = s
                        .meta
                        .claude_project
                        .as_ref()
                        .map(|p| p.thread_root_id.as_str())
                        .unwrap_or("");
                    let message = catalog.sessions[i]
                        .meta
                        .claude_project
                        .as_ref()
                        .and_then(|p| p.messages.iter().position(|m| m.id == root));
                    jump = Some(Jump {
                        session: i,
                        message,
                    });
                }
            }
        }
    });
    jump
}

pub(super) fn attach_links(catalog: &Catalog, selected: usize, cards: &mut [MessageCard]) {
    let s = &catalog.sessions[selected];
    let Some(project) = &s.meta.claude_project else {
        return;
    };
    // Explicit source identities align with the exported message sequence. An
    // interrupted/stale index must not attach actions to a different message.
    if project.messages.len() != cards.len()
        || project.messages.iter().zip(cards.iter()).any(|(m, c)| {
            m.timestamp != c.timestamp
                || m.role
                    != if c.role == "用户" {
                        "user"
                    } else {
                        "assistant"
                    }
        })
    {
        return;
    }
    let rows = related(catalog, selected);
    for (message, card) in project.messages.iter().zip(cards.iter_mut()) {
        card.project_thread = Some(if message.thread_root_id.is_empty() {
            message.id.clone()
        } else {
            message.thread_root_id.clone()
        });
        let mut roots = message.linked_thread_ids.clone();
        if is_main(s)
            && !message.thread_root_id.is_empty()
            && (message.has_thread
                || rows.iter().any(|&i| {
                    is_thread(&catalog.sessions[i])
                        && catalog.sessions[i]
                            .meta
                            .claude_project
                            .as_ref()
                            .is_some_and(|p| p.thread_root_id == message.thread_root_id)
                }))
        {
            roots.insert(0, message.thread_root_id.clone());
        }
        let mut seen = BTreeSet::new();
        for root in roots.into_iter().filter(|root| seen.insert(root.clone())) {
            if project.view == "thread" && root == project.thread_root_id {
                continue;
            }
            let target = rows.iter().copied().find(|&i| {
                is_thread(&catalog.sessions[i])
                    && catalog.sessions[i]
                        .meta
                        .claude_project
                        .as_ref()
                        .is_some_and(|p| p.thread_root_id == root)
            });
            let label = target
                .map(|i| {
                    let t = &catalog.sessions[i];
                    let state = t
                        .meta
                        .claude_project
                        .as_ref()
                        .map(|p| status(&p.status))
                        .unwrap_or("状态未知");
                    if root == message.thread_root_id {
                        format!("查看讨论串 · 已保存 {} 条消息 · {state}", t.meta.messages)
                    } else {
                        let title: String = t.display_title.chars().take(36).collect();
                        format!("关联讨论串：{title} · {state}")
                    }
                })
                .unwrap_or_else(|| "关联讨论串未缓存".into());
            card.project_links.push(Link {
                label,
                hint: target
                    .map(|i| catalog.sessions[i].display_title.clone())
                    .unwrap_or_else(|| "缓存中没有可读取的正文，无法打开未保存的讨论。".into()),
                target: target.map(|session| Jump {
                    session,
                    message: None,
                }),
            });
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn session(view: &str, product: &str) -> Session {
        let meta: SessionMeta = serde_json::from_value(serde_json::json!({
            "id": format!("{view}-{product}"), "tool": "claude-desktop", "project": "Fixture Projects",
            "project_id": "same-channel", "source": "code-projects-cache", "messages": 1,
            "claude_project": {"product": product, "channel_id": "same-channel", "view": view,
                "thread_root_id": if view == "main" { "" } else { "root" },
                "status": "needs_input", "messages": [{"id": "root", "thread_root_id": "root",
                    "role": "assistant", "timestamp": "2026-11-12T01:00:00Z", "has_thread": true}]}
        })).unwrap();
        Session {
            meta,
            display_title: view.into(),
            branch: "fixture-claude-desktop".into(),
            device: "fixture".into(),
            path: PathBuf::new(),
            search: String::new(),
            markdown: "## 助手 · 2026-11-12T01:00:00Z\n已完成任务。\n".into(),
        }
    }

    #[test]
    fn project_navigation_preserves_product_and_workdir_project_boundaries() {
        let mut ordinary = session("thread", "Claude");
        ordinary.meta.source = "claude-ai-chat".into();
        ordinary.meta.claude_project = None;
        let catalog = Catalog {
            sessions: vec![
                session("main", "Claude"),
                session("thread", "Claude"),
                session("main", "Claude-3p"),
                session("timeline_item", "Claude"),
                ordinary,
            ],
            ..Default::default()
        };
        assert_eq!(main(&catalog, 1), Some(0));
        assert_eq!(recent(&catalog, &[1, 0, 2, 4]), vec![1, 2, 4]);
        assert_ne!(
            project_identity(&catalog.sessions[0]),
            project_identity(&catalog.sessions[2])
        );
        assert_ne!(
            project_identity(&catalog.sessions[0]),
            project_identity(&catalog.sessions[4])
        );
        assert!(!Filters::default().matches(&catalog.sessions[3]));
        let mut cards = message_cards(body(&catalog.sessions[0].markdown));
        attach_links(&catalog, 0, &mut cards);
        assert_eq!(
            cards[0].project_links[0].target,
            Some(Jump {
                session: 1,
                message: None
            })
        );
        cards[0].timestamp = "stale timestamp".into();
        cards[0].project_links.clear();
        attach_links(&catalog, 0, &mut cards);
        assert!(cards[0].project_links.is_empty());
    }

    #[test]
    fn main_messages_stay_separate_and_timeline_roots_jump_to_one_original() {
        let mut main_session = session("main", "Claude");
        main_session
            .markdown
            .push_str("## 助手 · 2026-11-12T02:00:00Z\n已发布另一个成果。\n");
        main_session
            .meta
            .claude_project
            .as_mut()
            .unwrap()
            .messages
            .push(Message {
                id: "other-root".into(),
                thread_root_id: "other-root".into(),
                role: "assistant".into(),
                timestamp: "2026-11-12T02:00:00Z".into(),
                ..Default::default()
            });
        let mut catalog = Catalog {
            sessions: vec![main_session, session("thread", "Claude")],
            ..Default::default()
        };
        catalog.timelines = catalog
            .sessions
            .iter()
            .map(timeline::extract_session)
            .collect();
        let mut cards = message_cards(body(&catalog.sessions[0].markdown));
        attach_links(&catalog, 0, &mut cards);
        assert!(assistant_reply_groups(&cards).is_empty());
        assert!(
            cards[1].project_links.is_empty(),
            "standalone main messages are not fake discussions"
        );
        let entries = timeline_entries(&catalog, &[0, 1], "", false);
        assert_eq!(entries.len(), 2);
        assert!(entries.iter().any(|&(i, _)| i == 1));
        assert_eq!(
            timeline_entries(&catalog, &[0], "", false).len(),
            2,
            "filtering out the discussion must keep its main message searchable"
        );
    }

    #[test]
    fn discussion_button_opens_thread_and_back_returns_to_exact_main_message() {
        let catalog = Catalog {
            sessions: vec![session("main", "Claude"), session("thread", "Claude")],
            ..Default::default()
        };
        let ctx = egui::Context::default();
        let mut cards = message_cards(body(&catalog.sessions[0].markdown));
        attach_links(&catalog, 0, &mut cards);
        let mut cache = CommonMarkCache::default();
        let mut position = egui::Pos2::ZERO;
        let mut selected = 0;
        let mut result = None;
        for frame in 0..7 {
            let output = ctx.run(
                egui::RawInput {
                    screen_rect: Some(egui::Rect::from_min_size(
                        egui::Pos2::ZERO,
                        egui::vec2(760.0, 500.0),
                    )),
                    time: Some(frame as f64 / 60.0),
                    events: if frame == 0 || frame == 3 || frame == 4 {
                        vec![]
                    } else {
                        vec![
                            egui::Event::PointerMoved(position),
                            egui::Event::PointerButton {
                                pos: position,
                                button: egui::PointerButton::Primary,
                                pressed: frame == 1 || frame == 5,
                                modifiers: egui::Modifiers::NONE,
                            },
                        ]
                    },
                    ..Default::default()
                },
                |ctx| {
                    egui::CentralPanel::default().show(ctx, |ui| {
                        if selected == 0 {
                            if let Some(ReaderAction::Project(jump)) =
                                show_message_cards(ui, &mut cards, &mut cache, 320, None, &mut None)
                            {
                                result = Some(jump);
                            }
                        } else {
                            result = navigation(ui, &catalog, selected).or(result);
                        }
                    });
                },
            );
            fn locate(shape: &egui::Shape, needle: &str) -> Option<egui::Pos2> {
                match shape {
                    egui::Shape::Text(t) if t.galley.text().contains(needle) => {
                        Some(shape.visual_bounding_rect().center())
                    }
                    egui::Shape::Vec(shapes) => shapes.iter().find_map(|s| locate(s, needle)),
                    _ => None,
                }
            }
            if frame == 0 || frame == 4 {
                position = output
                    .shapes
                    .iter()
                    .find_map(|s| {
                        locate(
                            &s.shape,
                            if frame == 0 {
                                "查看讨论串"
                            } else {
                                "← 主对话"
                            },
                        )
                    })
                    .unwrap();
            }
            if frame == 2 {
                assert_eq!(
                    result,
                    Some(Jump {
                        session: 1,
                        message: None
                    })
                );
                selected = 1;
                result = None;
            }
        }
        assert_eq!(
            result,
            Some(Jump {
                session: 0,
                message: Some(0)
            })
        );
    }
}
