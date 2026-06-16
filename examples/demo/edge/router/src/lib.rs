//! Edge request router: maps a route to an HTTP status, gating private routes on auth.

pub enum Route {
    Health,
    Users,
    Orders,
    Unknown,
}

pub fn dispatch(route: Route, authenticated: bool) -> u16 {
    match route {
        Route::Health => 200,
        Route::Users => guard(authenticated),
        Route::Orders => guard(authenticated),
        Route::Unknown => 404,
    }
}

fn guard(authenticated: bool) -> u16 {
    if authenticated {
        200
    } else {
        401
    }
}
