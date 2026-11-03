<?php

return [

    'paths' => ['api/*'],

    'allowed_methods' => ['*'],

    // Vite dev server (5173) and the built dashboard served by FastAPI (8000), by name or by IP.
    'allowed_origins' => array_filter(array_map('trim', explode(',', env(
        'FRONTEND_ORIGINS',
        'http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000'
    )))),

    'allowed_origins_patterns' => [],

    'allowed_headers' => ['*'],

    'exposed_headers' => [],

    'max_age' => 0,

    'supports_credentials' => true,
];
