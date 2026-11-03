<?php

use App\Http\Controllers\AuthController;
use Illuminate\Support\Facades\Route;

Route::prefix('auth')->middleware(["throttle:10,1"])->group(function () {
    Route::post("login", [AuthController::class, 'login']);
    Route::post("register", [AuthController::class, 'register']);
    Route::post("refresh", [AuthController::class, 'refresh']);
});

Route::middleware('auth:api')->group(function () {
    Route::get("me", [AuthController::class, "me"]);
    Route::post("logout", [AuthController::class, 'logout']);
});
