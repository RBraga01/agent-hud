#include "gm_plugin_lvgl_api.h"

#include "agent_hud_renderer.h"
#include "agent_hud_state.h"
#include "agent_hud_theme.h"
#include "agent_hud_view.h"
#include "input_mapping.h"
#include "protocol.h"

#define DECISION_CAPACITY 512U

#ifndef AGENT_HUD_INPUT_MAPPING
#define AGENT_HUD_INPUT_MAPPING AH_MAPPING_B
#endif

typedef struct {
    const gm_plugin_host_api_t *host;
    const gm_plugin_lvgl_api_t *ui;
    ah_renderer_t renderer;
    ah_model_t model;
    ah_effect_t effect;
    ah_view_t view;
    ah_input_mapping_t mapping;
    ah_connectivity_t connectivity;
    bool session_locked;
    int16_t display_width;
    int16_t display_height;
} agent_hud_t;

static agent_hud_t s_agent_hud;

static bool same_identifier(const char *left, const char *right)
{
    size_t offset = 0U;
    if (left == 0 || right == 0) return false;
    while (offset <= AH_CORE_MAX_ID_BYTES) {
        if (left[offset] != right[offset]) return false;
        if (left[offset] == '\0') return true;
        ++offset;
    }
    return false;
}

static void render(agent_hud_t *self)
{
    if (ah_view_build(&self->model, self->mapping, self->connectivity,
                      &self->view)) {
        ah_theme_t theme = ah_theme_for_state(self->model.state);
        if (self->view.kind == AH_VIEW_OFFLINE)
            theme = ah_theme_for_state(AH_STATE_ERROR);
        if (!ah_renderer_render(&self->renderer, &self->view, theme))
            (void)ah_renderer_message(&self->renderer,
                                      "DISPLAY UNAVAILABLE",
                                      "The HUD state could not be drawn");
    } else
        (void)ah_renderer_message(&self->renderer, "DISPLAY UNAVAILABLE",
                                  "The HUD state is invalid");
}

static void receive_local_error(agent_hud_t *self)
{
    ah_result_t result = {
        .decision_id = self->model.in_flight.decision_id,
        .task_id = self->model.in_flight.task_id,
        .revision = self->model.in_flight.revision,
        .status = AH_RESULT_ERROR,
        .original_status = AH_RESULT_NONE,
        .retryable = true
    };
    ah_event_t event = {.type = AH_EVENT_RESULT_RECEIVED, .result = &result};
    (void)ah_transition(&self->model, &event);
}

static void transmit(agent_hud_t *self, const ah_core_decision_t *decision)
{
    ah_decision_t wire = {
        .decision_id = decision->decision_id,
        .task_id = decision->task_id,
        .revision = decision->revision,
        .action_id = decision->action_id
    };
    uint8_t *bytes = self->host->alloc(DECISION_CAPACITY);
    size_t length;
    if (bytes == 0) {
        receive_local_error(self);
        return;
    }
    length = ah_encode_decision(&wire, bytes, DECISION_CAPACITY);
    if (length == 0U || self->host->bt_send(AH_RESPONSE_CHANNEL, bytes,
                                            (uint32_t)length) != GM_PLUGIN_OK)
        receive_local_error(self);
    self->host->free(bytes);
}

static void apply_event(agent_hud_t *self, ah_event_t *event)
{
    self->effect = ah_transition(&self->model, event);
    if (self->effect.type == AH_EFFECT_SEND_DECISION)
        transmit(self, &self->effect.decision);
    render(self);
}

static gm_plugin_result_t agent_hud_start(void *context)
{
    agent_hud_t *self = context;
    gm_plugin_display_info_t display;
    gm_plugin_lvgl_obj_t *root = self->ui->root_get();
    if (root == 0 ||
        self->host->display_get_info(&display) != GM_PLUGIN_OK ||
        display.width < AH_RENDERER_WIDTH ||
        display.height < AH_RENDERER_HEIGHT)
        return GM_PLUGIN_ESTATE;
    if (!ah_renderer_start(&self->renderer, self->ui, root,
                           (int16_t)display.width,
                           (int16_t)display.height))
        return GM_PLUGIN_ENOMEM;
    self->mapping = (ah_input_mapping_t)AGENT_HUD_INPUT_MAPPING;
    self->connectivity = AH_CONNECTIVITY_UNKNOWN;
    self->session_locked = false;
    self->display_width = (int16_t)display.width;
    self->display_height = (int16_t)display.height;
    ah_model_init(&self->model, "unbound");
    if (self->host->imu_enable != 0)
        (void)self->host->imu_enable(GM_PLUGIN_IMU_ENABLE_GESTURES);
    render(self);
    return GM_PLUGIN_OK;
}

static bool handle_task(agent_hud_t *self, const uint8_t *bytes, size_t length)
{
    ah_request_t request;
    uint8_t index;
    ah_core_task_t task = {
        .task_id = 0,
        .revision = 0U,
        .title = 0,
        .short_context = 0,
        .action_count = 0U,
        .actions = {{.action_id = 0, .label = 0}}
    };
    ah_event_t event = {.type = AH_EVENT_REQUEST_ARRIVED, .task = &task};
    if (!ah_decode_request(bytes, length, &request)) return false;
    if (!self->session_locked) {
        if (!same_identifier(self->model.session_id, request.session_id))
            ah_model_init(&self->model, request.session_id);
        self->session_locked = true;
    } else if (!same_identifier(self->model.session_id, request.session_id)) {
        (void)ah_renderer_message(&self->renderer, "SESSION CHANGED",
                                  "Restart the paired app");
        return true;
    }
    task.task_id = request.task_id;
    task.revision = request.revision;
    task.title = request.title;
    task.short_context = request.short_context;
    task.action_count = request.action_count;
    for (index = 0U; index < request.action_count; ++index) {
        task.actions[index].action_id = request.actions[index].action_id;
        task.actions[index].label = request.actions[index].label;
    }
    apply_event(self, &event);
    return true;
}

static bool handle_result(agent_hud_t *self, const uint8_t *bytes, size_t length)
{
    ah_wire_result_t wire;
    ah_result_t result;
    ah_event_t event = {.type = AH_EVENT_RESULT_RECEIVED, .result = &result};
    if (!ah_decode_result(bytes, length, &wire)) return false;
    result.decision_id = wire.decision_id;
    result.task_id = wire.task_id;
    result.revision = wire.revision;
    result.status = (ah_result_status_t)wire.status;
    result.original_status = (ah_result_status_t)wire.original_status;
    result.retryable = wire.status == (uint8_t)AH_RESULT_ERROR;
    apply_event(self, &event);
    return true;
}

static bool handle_message(agent_hud_t *self, const gm_plugin_event_t *event)
{
    const uint8_t *bytes;
    size_t length;
    if (event->data.bt.channel != AH_REQUEST_CHANNEL) return false;
    bytes = event->data.bt.data;
    length = event->data.bt.length;
    if (handle_task(self, bytes, length) || handle_result(self, bytes, length))
        return true;
    (void)ah_renderer_message(&self->renderer, "MESSAGE REJECTED",
                              "The phone sent invalid data");
    return true;
}

static bool apply_physical_input(agent_hud_t *self, ah_physical_input_t input)
{
    ah_event_type_t type;
    ah_event_t event;
    if (!ah_map_input(self->mapping, self->model.state, input, &type))
        return false;
    event.type = type;
    event.task = 0;
    event.task_id = 0;
    event.result = 0;
    apply_event(self, &event);
    return true;
}

static bool handle_button(agent_hud_t *self,
                          const gm_plugin_event_t *event)
{
    if (event->data.button.button == GM_PLUGIN_BUTTON_BACK &&
        event->data.button.action == GM_PLUGIN_BUTTON_ACTION_TRIGGER)
        return apply_physical_input(self, AH_INPUT_BACK);
    if (event->data.button.button != GM_PLUGIN_BUTTON_PRIMARY) return false;
    if (event->data.button.action == GM_PLUGIN_BUTTON_ACTION_SINGLE)
        return apply_physical_input(self, AH_INPUT_PRIMARY_SINGLE);
    if (event->data.button.action == GM_PLUGIN_BUTTON_ACTION_DOUBLE)
        return apply_physical_input(self, AH_INPUT_PRIMARY_DOUBLE);
    return false;
}

static bool handle_head(agent_hud_t *self, const gm_plugin_event_t *event)
{
    if (!event->data.imu_gesture.active) return false;
    if (event->data.imu_gesture.gesture == GM_PLUGIN_IMU_GESTURE_LEFT)
        return apply_physical_input(self, AH_INPUT_HEAD_LEFT);
    if (event->data.imu_gesture.gesture == GM_PLUGIN_IMU_GESTURE_RIGHT)
        return apply_physical_input(self, AH_INPUT_HEAD_RIGHT);
    if (event->data.imu_gesture.gesture == GM_PLUGIN_IMU_GESTURE_SHAKE)
        return apply_physical_input(self, AH_INPUT_HEAD_SHAKE);
    return false;
}

static bool agent_hud_event(void *context, const gm_plugin_event_t *event)
{
    agent_hud_t *self = context;
    if (event == 0) return false;
    if (event->type == GM_PLUGIN_EVENT_CONNECTION) {
        self->connectivity = event->data.connection.connected
            ? AH_CONNECTIVITY_CONNECTED : AH_CONNECTIVITY_DISCONNECTED;
        if (!event->data.connection.connected) {
            ah_event_t lost = {.type = AH_EVENT_CONNECTION_LOST};
            self->session_locked = false;
            apply_event(self, &lost);
        } else {
            render(self);
        }
        return true;
    }
    if (event->type == GM_PLUGIN_EVENT_BT_MESSAGE)
        return handle_message(self, event);
    if (event->type == GM_PLUGIN_EVENT_BUTTON)
        return handle_button(self, event);
    if (event->type == GM_PLUGIN_EVENT_IMU_GESTURE)
        return handle_head(self, event);
    return false;
}

static void agent_hud_stop(void *context)
{
    agent_hud_t *self = context;
    gm_plugin_lvgl_obj_t *root = self->ui->root_get();
    if (self->host->imu_enable != 0)
        (void)self->host->imu_enable(GM_PLUGIN_IMU_ENABLE_NONE);
    if (root != 0) self->ui->obj_clean(root);
    ah_renderer_stop(&self->renderer);
    self->session_locked = false;
    ah_model_init(&self->model, "stopped");
}

gm_plugin_result_t gm_plugin_entry(const gm_plugin_host_api_t *host,
                                   gm_plugin_descriptor_t *plugin)
{
    const gm_plugin_capabilities_t required =
        GM_PLUGIN_CAP_BLUETOOTH | GM_PLUGIN_CAP_BUTTON;
    if (host == 0 || plugin == 0 || host->bt_send == 0 ||
        host->alloc == 0 || host->free == 0 ||
        host->display_get_info == 0 || host->graphics.lvgl == 0 ||
        !GM_PLUGIN_VERSION_COMPATIBLE(host->abi_version,
                                      GM_PLUGIN_ABI_MIN_VERSION) ||
        host->struct_size < GM_PLUGIN_HOST_API_MIN_SIZE ||
        plugin->struct_size < GM_PLUGIN_DESCRIPTOR_MIN_SIZE ||
        (host->capabilities & required) != required)
        return GM_PLUGIN_ENOTSUP;
    s_agent_hud.host = host;
    s_agent_hud.ui = host->graphics.lvgl;
    if (s_agent_hud.ui->struct_size < GM_PLUGIN_LVGL_API_MIN_SIZE ||
        !GM_PLUGIN_VERSION_COMPATIBLE(s_agent_hud.ui->api_version,
                                      GM_PLUGIN_LVGL_API_MIN_VERSION))
        return GM_PLUGIN_EVERSION;
    plugin->abi_version = GM_PLUGIN_ABI_MIN_VERSION;
    plugin->context = &s_agent_hud;
    plugin->on_start = agent_hud_start;
    plugin->on_event = agent_hud_event;
    plugin->on_stop = agent_hud_stop;
    return GM_PLUGIN_OK;
}
