const express = require('express');
const usersController = require('./users.controller');
const authMiddleware = require('../../common/middlewares/auth.middleware');
const roleMiddleware = require('../../common/middlewares/role.middleware');
const {
  updateProfileRules,
  changePasswordRules,
  updateRoleRules,
  queryUsersRules,
  validate
} = require('./users.validation');

const usersRouter = express.Router();
const adminUsersRouter = express.Router();

/**
 * @openapi
 * tags:
 *   name: Users
 *   description: Personal profile management
 */

/**
 * @openapi
 * tags:
 *   name: Admin Users
 *   description: Administrator tools for managing users and roles
 */

// ==========================================
// 1. Personal Profile Routes (/api/users)
// ==========================================

/**
 * @openapi
 * /api/users/me:
 *   get:
 *     summary: View personal profile
 *     description: Retrieve details of the current logged-in user.
 *     tags: [Users]
 *     security:
 *       - bearerAuth: []
 *     responses:
 *       200:
 *         description: Profile successfully retrieved.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Get profile successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     id:
 *                       type: string
 *                       example: 665f1a2b9c1e2a0012a12345
 *                     full_name:
 *                       type: string
 *                       example: Nguyen Van A
 *                     email:
 *                       type: string
 *                       example: user@gmail.com
 *                     role:
 *                       type: string
 *                       example: USER
 *                     status:
 *                       type: string
 *                       example: ACTIVE
 *                     created_at:
 *                       type: string
 *                       format: date-time
 *                       example: 2026-06-01T10:00:00.000Z
 *       401:
 *         description: Unauthorized. Missing or invalid Bearer access token.
 *       403:
 *         description: Forbidden. Account is locked.
 */
usersRouter.get('/me', authMiddleware, usersController.getMe);

/**
 * @openapi
 * /api/users/me:
 *   put:
 *     summary: Update personal profile
 *     description: Modify name details of the logged-in user.
 *     tags: [Users]
 *     security:
 *       - bearerAuth: []
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - full_name
 *             properties:
 *               full_name:
 *                 type: string
 *                 minLength: 2
 *                 maxLength: 100
 *                 example: Nguyen Van B
 *     responses:
 *       200:
 *         description: Profile successfully updated.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Update profile successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     id:
 *                       type: string
 *                       example: 665f1a2b9c1e2a0012a12345
 *                     full_name:
 *                       type: string
 *                       example: Nguyen Van B
 *                     email:
 *                       type: string
 *                       example: user@gmail.com
 *                     role:
 *                       type: string
 *                       example: USER
 *                     status:
 *                       type: string
 *                       example: ACTIVE
 *       400:
 *         description: Validation failed.
 *       401:
 *         description: Unauthorized.
 */
usersRouter.put('/me', authMiddleware, updateProfileRules, validate, usersController.updateMe);

/**
 * @openapi
 * /api/users/me/password:
 *   put:
 *     summary: Change personal password
 *     description: Change user password and terminate other active refresh sessions.
 *     tags: [Users]
 *     security:
 *       - bearerAuth: []
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - current_password
 *               - new_password
 *             properties:
 *               current_password:
 *                 type: string
 *                 example: OldPassword123
 *               new_password:
 *                 type: string
 *                 minLength: 8
 *                 example: NewPassword123
 *     responses:
 *       200:
 *         description: Password changed successfully.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Change password successfully
 *       400:
 *         description: Bad Request. Current password incorrect, or new password matches old password.
 *       401:
 *         description: Unauthorized.
 */
usersRouter.put('/me/password', authMiddleware, changePasswordRules, validate, usersController.changePassword);

// ==========================================
// 2. Admin Management Routes (/api/admin/users)
// ==========================================

/**
 * @openapi
 * /api/admin/users:
 *   get:
 *     summary: List and search users
 *     description: Retrieve paginated list of users with filtering options.
 *     tags: [Admin Users]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: query
 *         name: page
 *         schema:
 *           type: integer
 *           minimum: 1
 *           default: 1
 *       - in: query
 *         name: limit
 *         schema:
 *           type: integer
 *           minimum: 1
 *           maximum: 100
 *           default: 10
 *       - in: query
 *         name: keyword
 *         schema:
 *           type: string
 *         description: Search by name or email
 *       - in: query
 *         name: status
 *         schema:
 *           type: string
 *           enum: [ACTIVE, LOCKED]
 *       - in: query
 *         name: role
 *         schema:
 *           type: string
 *           enum: [USER, STAFF, ADMIN]
 *     responses:
 *       200:
 *         description: Paginated users retrieved.
 *         content:
 *           application/json:
 *             schema:
 *               type: object
 *               properties:
 *                 success:
 *                   type: boolean
 *                   example: true
 *                 message:
 *                   type: string
 *                   example: Get users successfully
 *                 data:
 *                   type: object
 *                   properties:
 *                     items:
 *                       type: array
 *                       items:
 *                         type: object
 *                     pagination:
 *                       type: object
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden. Insufficient permission (must be ADMIN).
 */
adminUsersRouter.get('/', authMiddleware, roleMiddleware(['ADMIN']), queryUsersRules, validate, usersController.adminGetUsers);

/**
 * @openapi
 * /api/admin/users/{id}:
 *   get:
 *     summary: View user details
 *     description: Retrieve profile information of a specific user.
 *     tags: [Admin Users]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *         description: Target User ID
 *     responses:
 *       200:
 *         description: Profile details retrieved.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: User not found.
 */
adminUsersRouter.get('/:id', authMiddleware, roleMiddleware(['ADMIN']), usersController.adminGetUserById);

/**
 * @openapi
 * /api/admin/users/{id}/lock:
 *   patch:
 *     summary: Lock user account
 *     description: Restrict user from logging in and invalidate active sessions.
 *     tags: [Admin Users]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *         description: Target User ID
 *     responses:
 *       200:
 *         description: User successfully locked.
 *       400:
 *         description: Bad Request. Admin cannot self-lock or lock other Admin accounts.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: User not found.
 */
adminUsersRouter.patch('/:id/lock', authMiddleware, roleMiddleware(['ADMIN']), usersController.adminLockUser);

/**
 * @openapi
 * /api/admin/users/{id}/unlock:
 *   patch:
 *     summary: Unlock user account
 *     description: Re-enable user access to log in.
 *     tags: [Admin Users]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *         description: Target User ID
 *     responses:
 *       200:
 *         description: User successfully unlocked.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: User not found.
 */
adminUsersRouter.patch('/:id/unlock', authMiddleware, roleMiddleware(['ADMIN']), usersController.adminUnlockUser);

/**
 * @openapi
 * /api/admin/users/{id}/role:
 *   patch:
 *     summary: Update user role
 *     description: Assign USER or STAFF role to the target user.
 *     tags: [Admin Users]
 *     security:
 *       - bearerAuth: []
 *     parameters:
 *       - in: path
 *         name: id
 *         required: true
 *         schema:
 *           type: string
 *         description: Target User ID
 *     requestBody:
 *       required: true
 *       content:
 *         application/json:
 *           schema:
 *             type: object
 *             required:
 *               - role
 *             properties:
 *               role:
 *                 type: string
 *                 enum: [USER, STAFF]
 *                 example: STAFF
 *     responses:
 *       200:
 *         description: Role successfully updated.
 *       400:
 *         description: Bad Request. Invalid role value.
 *       401:
 *         description: Unauthorized.
 *       403:
 *         description: Forbidden.
 *       404:
 *         description: User not found.
 */
adminUsersRouter.patch('/:id/role', authMiddleware, roleMiddleware(['ADMIN']), updateRoleRules, validate, usersController.adminUpdateUserRole);

module.exports = {
  usersRouter,
  adminUsersRouter
};
